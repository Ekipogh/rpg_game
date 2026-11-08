import json
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import models

from hero.encounters import ENCOUNTER_DEFINITIONS
from .engine import snapshot_from_json, state_from_json


class Battle(models.Model):
    id = models.AutoField(primary_key=True)
    hero = models.ForeignKey("hero.Hero", on_delete=models.CASCADE)
    encounter_id = models.UUIDField(unique=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("PENDING", "Pending"),
            ("ACTIVE", "Active"),
            ("RESOLVING", "Resolving"),
            ("FINISHED", "Finished"),
            ("PAUSED_ERROR", "Paused with Error"),
        ],
        default="PENDING",
    )
    snapshot = models.JSONField(null=True, blank=True)
    checkpoint = models.JSONField(null=True, blank=True)
    revision = models.PositiveBigIntegerField(default=0)
    next_due_at = models.DateTimeField(null=True, blank=True)
    last_event_sequence = models.PositiveBigIntegerField(default=0)
    last_processed_command_sequence = models.PositiveBigIntegerField(default=0)

    outcome = models.CharField(
        max_length=20,
        choices=[
            ("VICTORY", "Victory"),
            ("DEFEAT", "Defeat"),
        ],
        null=True,
        blank=True,
    )

    error_code = models.CharField(max_length=100, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "next_due_at"], name="battle_due_idx")]
        constraints = [
            models.UniqueConstraint(fields=["hero"], condition=~models.Q(status="FINISHED"),
                                    name="one_open_battle_per_hero"),
            models.CheckConstraint(condition=models.Q(status__in=["PENDING", "ACTIVE", "RESOLVING", "FINISHED", "PAUSED_ERROR"]), name="battle_valid_status"),
            models.CheckConstraint(condition=models.Q(outcome__isnull=True) | models.Q(outcome__in=["VICTORY", "DEFEAT"]), name="battle_valid_outcome"),
        ]

    def clean(self):
        super().clean()
        requires_state = self.status in {"ACTIVE", "RESOLVING", "FINISHED"}
        if requires_state and (self.snapshot is None or self.checkpoint is None):
            raise ValidationError("Active and completed battles require snapshot and checkpoint.")
        if self.checkpoint is not None and self.snapshot is None:
            raise ValidationError({"checkpoint": "A checkpoint requires a snapshot."})
        if self.snapshot is None:
            return
        try:
            snapshot = snapshot_from_json(json.dumps(self.snapshot))
            if self.pk is not None and snapshot.battle_id != str(self.pk):
                raise ValueError("Snapshot battle ID does not match this record.")
            if snapshot.encounter_id != str(self.encounter_id):
                raise ValueError("Snapshot encounter ID does not match this record.")
            if self.checkpoint is not None:
                state = state_from_json(snapshot, json.dumps(self.checkpoint))
                if (state.last_event_sequence != self.last_event_sequence or
                        state.last_processed_command_sequence != self.last_processed_command_sequence):
                    raise ValueError("Checkpoint sequence cursors do not match record.")
                if self.status == "ACTIVE" and state.phase != "active":
                    raise ValueError("Active battle requires an active checkpoint.")
                if self.status in {"RESOLVING", "FINISHED"} and state.phase != "finished":
                    raise ValueError("Completed battle requires a finished checkpoint.")
                expected_outcome = state.outcome.result.upper() if state.outcome else None
                if self.outcome != expected_outcome:
                    raise ValueError("Outcome does not match checkpoint.")
        except (ValueError, TypeError) as exc:
            raise ValidationError({"snapshot": str(exc)}) from exc


class BattleEvent(models.Model):
    id = models.AutoField(primary_key=True)
    battle = models.ForeignKey(
        Battle, on_delete=models.CASCADE, related_name="events"
    )
    sequence = models.PositiveBigIntegerField()
    simulation_time_ms = models.PositiveBigIntegerField()
    event_type = models.CharField(max_length=100)
    actor_id = models.CharField(max_length=100, null=True, blank=True)
    target_id = models.CharField(max_length=100, null=True, blank=True)
    payload = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["battle", "sequence"], name="battle_event_sequence_unique")
        ]


class BattleCommand(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    battle = models.ForeignKey(
        Battle, on_delete=models.CASCADE, related_name="commands"
    )
    sequence = models.PositiveBigIntegerField()
    command_type = models.CharField(max_length=100)
    payload = models.JSONField(null=True, blank=True)
    execute_at_ms = models.PositiveBigIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("QUEUED", "Queued"),
            ("ACCEPTED", "Accepted"),
            ("REJECTED", "Rejected"),
        ],
        default="QUEUED",
    )
    reject_reason = models.TextField(null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)


    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["battle", "sequence"], name="battle_command_sequence_unique"),
            models.CheckConstraint(condition=models.Q(status__in=["QUEUED", "ACCEPTED", "REJECTED"]), name="battle_command_valid_status"),
        ]


class BattleWorkerLease(models.Model):
    name = models.CharField(max_length=100, unique=True)
    owner_token = models.CharField(max_length=50)
    expires_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)


class EncounterMonster(models.Model):
    encounter_definition_key = models.CharField(max_length=100)
    monster = models.ForeignKey("hero.Monster", on_delete=models.PROTECT)
    quantity = models.PositiveSmallIntegerField(default=1)
    position_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position_order", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["encounter_definition_key", "position_order"],
                name="encounter_spawn_order_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1, quantity__lte=3),
                name="encounter_quantity_range",
            ),
        ]

    def clean(self):
        super().clean()
        definition = ENCOUNTER_DEFINITIONS.get(self.encounter_definition_key)
        if definition is None or definition.kind != "battle":
            raise ValidationError(
                {"encounter_definition_key": "Choose an existing battle encounter."}
            )
        if type(self.quantity) is not int or not 1 <= self.quantity <= 3:
            raise ValidationError(
                {"quantity": "Quantity must be between one and three."}
            )
        others = type(self).objects.filter(
            encounter_definition_key=self.encounter_definition_key
        )
        if self.pk is not None:
            others = others.exclude(pk=self.pk)
        total = others.aggregate(total=models.Sum("quantity"))["total"] or 0
        if total + self.quantity > 3:
            raise ValidationError(
                {"quantity": "Encounter cannot contain more than three enemies."}
            )
