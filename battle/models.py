from django.db import models


class Battle(models.Model):
    id = models.AutoField(primary_key=True)
    hero = models.ForeignKey("Hero", on_delete=models.CASCADE)
    encounter_id = models.IntegerField()
    status = models.CharField(
        max_length=20,
        choices=[
            ("PENDING", "Pending"),
            ("ACTIVE", "Active"),
            ("FINISHED", "Finished"),
            ("PAUSED_ERROR", "Paused with Error"),
        ],
    )
    snapshot = models.JSONField(null=True, blank=True)
    checkpoint = models.JSONField(null=True, blank=True)
    revision = models.IntegerField(default=0)
    next_due_at = models.DateTimeField(null=True, blank=True)
    last_event_sequence = models.IntegerField(default=0)
    last_processed_command_sequence = models.IntegerField(default=0)

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
