"""Transactional adapter between the pure engine and Django persistence.

SQLite writes are serialized by fencing the worker lease as the first statement
of each transaction. Simulation batches are capped at one second.
"""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
import json
import secrets

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from hero.dungeon import _snapshot, generate_paths
from hero.encounters import ENCOUNTER_DEFINITIONS, Encounter
from hero.models import Hero
from item.models import EquipmentSlot, Item, Instant
from item.services import receive_item
from .engine import (
    BattleCommandInput, BattleRules, BattleSnapshot, CombatStats,
    CombatantSnapshot, LootEntry, RewardSnapshot, SimulationLimitReached,
    SCHEMA_VERSION, RULES_VERSION, RNG_VERSION, advance, create_battle,
    snapshot_from_json, snapshot_to_json, state_from_json, state_to_json,
)
from .models import Battle, BattleCommand, BattleEvent, BattleWorkerLease, EncounterMonster

LEASE_NAME = "battle-worker"
LEASE_SECONDS = 15
MAX_BATCH_MS = 1000


def loot_report(drops):
    """Group awarded stacks by item for display; never roll or grant rewards."""
    quantities = {}
    for drop in drops:
        item_id, quantity = drop["item_id"], drop["quantity"]
        quantities[item_id] = quantities.get(item_id, 0) + quantity
    names = dict(Item.objects.filter(pk__in=quantities).values_list("pk", "name"))
    return [{"item_id": item_id, "name": names.get(item_id, f"Item #{item_id}"),
             "quantity": quantity} for item_id, quantity in sorted(quantities.items())]


def submit_command(battle_id, hero_id, command_id, command_type, payload):
    """Allocate receipt order while holding a database write lock.

    The first update serializes producers with the daemon on SQLite; select_for_update
    alone would not lock SQLite. Failed validation rolls that update back.
    """
    from django.db.models import Max
    with transaction.atomic():
        if not Battle.objects.filter(pk=battle_id, hero_id=hero_id).update(
                revision=F("revision") + 1, updated_at=timezone.now()):
            raise Battle.DoesNotExist
        battle = Battle.objects.get(pk=battle_id)
        existing = BattleCommand.objects.filter(pk=command_id).first()
        if existing:
            if (existing.battle_id != battle_id or existing.command_type != command_type or
                    existing.payload != payload):
                raise BattleConflict("Command ID was already used for a different request")
            return existing, False
        if battle.status not in {"PENDING", "ACTIVE"}:
            raise BattleConflict("This battle is not accepting commands")
        hero = Hero.objects.get(pk=hero_id)
        _encounter(hero, battle)
        if command_type == "set_movement_policy":
            if set(payload) != {"policy"} or payload["policy"] not in ("approach", "hold"):
                raise ValueError("Choose Approach or Hold")
        elif command_type == "select_target":
            if set(payload) != {"target_id"} or type(payload["target_id"]) is not str:
                raise ValueError("Specify a target")
            snapshot, state = battle.snapshot, battle.checkpoint
            if not snapshot or not state or not any(
                    actor["combatant_id"] == payload["target_id"] and actor["team"] == "enemy" and
                    state["combatants"][actor["combatant_id"]]["health"] > 0
                    for actor in snapshot["combatants"]):
                raise ValueError("Target is unavailable")
        else:
            raise ValueError("Unsupported command")
        if battle.commands.filter(status="QUEUED").count() >= 100:
            raise BattleConflict("Too many pending commands; wait for the battle to advance")
        last = battle.commands.aggregate(last=Max("sequence"))["last"] or 0
        command = BattleCommand.objects.create(id=command_id, battle=battle,
            sequence=max(last, battle.last_processed_command_sequence) + 1,
            command_type=command_type, payload=payload)
        return command, True


class LeaseLost(RuntimeError):
    pass


class BattleConflict(RuntimeError):
    pass


def acquire_lease(token):
    now = timezone.now()
    BattleWorkerLease.objects.get_or_create(name=LEASE_NAME, defaults={
        "owner_token": "", "expires_at": now,
    })
    return bool(BattleWorkerLease.objects.filter(name=LEASE_NAME).filter(
        Q(expires_at__lte=now) | Q(expires_at__isnull=True)
    ).update(owner_token=token, heartbeat_at=now,
             expires_at=now + timedelta(seconds=LEASE_SECONDS)))


def fence(token):
    now = timezone.now()
    if not BattleWorkerLease.objects.filter(name=LEASE_NAME, owner_token=token,
            expires_at__gt=now).update(heartbeat_at=now,
            expires_at=now + timedelta(seconds=LEASE_SECONDS)):
        raise LeaseLost("Battle worker lease expired or belongs to another process")


def release_lease(token):
    BattleWorkerLease.objects.filter(name=LEASE_NAME, owner_token=token).update(
        owner_token="", expires_at=timezone.now())


def _encounter(hero, battle=None):
    run = hero.dungeon_run
    if not run or run.get("phase") != "encounter" or not hero.is_in_combat:
        raise BattleConflict("Hero is no longer in a combat encounter")
    encounter = Encounter.from_dict(run["current_encounter"])
    if encounter.kind != "battle" or encounter.floor != run["current_floor"]:
        raise BattleConflict("Invalid battle encounter")
    if battle is not None and str(battle.encounter_id) != encounter.id:
        raise BattleConflict("Hero has moved to a different encounter")
    return encounter


def discover_battles(token, limit=100):
    """Adopt saved encounters, including runs created before the worker existed."""
    if limit <= 0:
        return 0
    # Choices and peaceful encounters retain is_in_combat for resource recovery.
    # Exclude them and managed heroes before bounding candidates, not creations:
    # even a candidate rejected on revalidation must consume the tick's budget.
    managed = Battle.objects.exclude(status="FINISHED").values("hero_id")
    battle_keys = [key for key, definition in ENCOUNTER_DEFINITIONS.items()
                   if definition.kind == "battle"]
    ids = list(Hero.objects.filter(is_in_combat=True,
               dungeon_run__phase="encounter",
               dungeon_run__current_encounter__definition_key__in=battle_keys)
               .exclude(pk__in=managed).order_by("pk").values_list("pk", flat=True)[:limit])
    created = 0
    for hero_id in ids:
        with transaction.atomic():
            fence(token)
            try:
                hero = Hero.objects.get(pk=hero_id)
                encounter = _encounter(hero)
            except (Hero.DoesNotExist, BattleConflict, ValueError, KeyError, TypeError):
                continue
            if not Battle.objects.filter(encounter_id=encounter.id).exists():
                Battle.objects.create(hero=hero, encounter_id=encounter.id)
                created += 1
    return created


def _stats(source, equipment=()):
    values = {name: getattr(source, name) for name in (
        "max_health", "max_mana", "attack", "defense", "magic", "magic_defense",
        "speed", "accuracy", "evasion", "critical_chance")}
    for item in equipment:
        for stat, bonus in (("attack", "attack_bonus"), ("accuracy", "accuracy_bonus"),
                ("defense", "defense_bonus"), ("magic", "magic_bonus"),
                ("magic_defense", "magic_defense_bonus"), ("speed", "speed_bonus"),
                ("critical_chance", "critical_bonus")):
            values[stat] += getattr(item, bonus, 0)
    values["critical_damage_bp"] = int((Decimal(str(source.critical_damage)) * 10000)
                                        .quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return CombatStats(**values)


def build_snapshot(battle, hero):
    encounter = _encounter(hero, battle)
    entries = list(EncounterMonster.objects.filter(encounter_definition_key=encounter.definition_key)
                   .select_related("monster").prefetch_related("monster__loot"))
    if not entries or not 1 <= sum(e.quantity for e in entries) <= 3:
        raise ValueError(f"Configure one to three monsters for {encounter.definition_key}")
    equipment = [slot.item for slot in EquipmentSlot.objects.filter(equipment__hero=hero)
                 .prefetch_related("item") if slot.item is not None]
    actors = [CombatantSnapshot("hero", "hero", "hero", hero.pk, hero.name,
        _stats(hero, equipment), 1, 1, hero.current_health, hero.current_mana, 0, "approach", None)]
    for entry in entries:
        monster = entry.monster
        rewards = RewardSnapshot(monster.experience_reward, tuple(
            LootEntry(loot.item_id, int(loot.drop_chance * 100), loot.min_quantity, loot.max_quantity)
            for loot in monster.loot.all().order_by("pk")))
        for _ in range(entry.quantity):
            index = len(actors) - 1
            actors.append(CombatantSnapshot(f"enemy:{index}", "enemy", "monster", monster.pk,
                monster.name, _stats(monster), 1, 1, monster.max_health, monster.max_mana,
                8 - index, "approach", rewards))
    return BattleSnapshot(SCHEMA_VERSION, RULES_VERSION, RNG_VERSION, str(battle.pk),
        str(battle.encounter_id), encounter.definition_key, encounter.floor, str(encounter.battle_tier),
        BattleRules(9, 1000, 600000, 334, 2000, 20), tuple(actors), secrets.token_hex(32))


def _resolve(battle, hero, snapshot, state):
    encounter = _encounter(hero, battle)
    hero_state = state.combatants["hero"]
    outcome = state.outcome
    run = deepcopy(hero.dungeon_run)
    if outcome.result == "defeat" or snapshot.battle_tier == "boss":
        run = {}
    else:
        run["last_result"] = {
            "health_change": hero_state.health - snapshot.combatants[0].initial_health,
            "experience_change": outcome.experience, "survived": True,
            "title": encounter.definition.title,
            "loot": loot_report([{"item_id": drop.item_id, "quantity": drop.quantity}
                                 for drop in outcome.loot]),
        }
        run["phase"] = "choices"
        run["hero_level"] = hero.level
        if encounter.battle_tier == "miniboss":
            run["miniboss_defeated"] = True
            run["regular_victories"] = 0
        elif encounter.battle_tier == "enemy":
            run["regular_victories"] = run.get("regular_victories", 0) + 1
        run.update(generate_paths(run["current_floor"] + 1, run=run))
    if not _snapshot(hero).update(current_health=max(1, hero_state.health),
            current_mana=hero_state.mana, experience=F("experience") + outcome.experience,
            dungeon_run=run, is_in_combat=bool(run),
            dungeon_revision=F("dungeon_revision") + 1):
        raise BattleConflict("Hero changed during battle resolution")
    # First persist the engine's final resources, then apply receipt effects so
    # healing/mana rewards cannot be overwritten by the combat checkpoint.
    hero.refresh_from_db()
    items = Item.objects.in_bulk({drop.item_id for drop in outcome.loot})
    money_change = 0
    for drop in outcome.loot:
        item = items[drop.item_id]
        effects = receive_item(hero, item, drop.quantity)
        money_change += effects["money_change"]
        if isinstance(item, Instant):
            state.last_event_sequence += 1
            BattleEvent.objects.create(battle=battle, sequence=state.last_event_sequence,
                simulation_time_ms=state.simulation_time_ms, event_type="instant_use",
                actor_id="hero", target_id="hero", payload={"item_id": item.pk,
                    "name": item.name, "quantity": drop.quantity, **effects})
    if outcome.result == "victory":
        hero_state.health, hero_state.mana = hero.current_health, hero.current_mana
    if run:
        run["last_result"]["money_change"] = money_change
        run["last_result"]["health_change"] = hero.current_health - snapshot.combatants[0].initial_health
        Hero.objects.filter(pk=hero.pk).update(dungeon_run=run)
    battle.status = "FINISHED"
    battle.finished_at = battle.finished_at or timezone.now()
    battle.resolved_at = timezone.now()
    battle.next_due_at = None


def process_battle(battle_id, token, elapsed_ms):
    """Advance and persist one bounded batch. Returns new status.

    First lease write locks SQLite before any reads. Revision checks protect
    against stale administrative changes; a final fence rejects expired owners.
    All checkpoint, resource, event, command and reward writes share this transaction.
    """
    if type(elapsed_ms) is not int or not 0 <= elapsed_ms <= MAX_BATCH_MS:
        raise ValueError("Invalid simulation batch length")
    with transaction.atomic():
        fence(token)
        battle = Battle.objects.select_related("hero").get(pk=battle_id)
        if battle.status not in {"PENDING", "ACTIVE", "RESOLVING"}:
            return battle.status
        revision = battle.revision
        hero = battle.hero
        _encounter(hero, battle)
        if battle.resolved_at is not None:
            raise BattleConflict("Battle rewards have already been resolved")
        now = timezone.now()
        if battle.snapshot is None:
            if battle.status != "PENDING":
                raise ValueError("Running battle has no snapshot")
            snapshot = build_snapshot(battle, hero)
            state = create_battle(snapshot)
            battle.snapshot = json.loads(snapshot_to_json(snapshot))
            battle.started_at = now
            elapsed_ms = 0  # Setup time is not simulated.
        else:
            battle.full_clean()
            snapshot = snapshot_from_json(json.dumps(battle.snapshot))
            state = state_from_json(snapshot, json.dumps(battle.checkpoint))
            hero_definition = next(c for c in snapshot.combatants if c.team == "hero")
            if hero_definition.source_id != hero.pk or hero_definition.combatant_id != "hero":
                raise BattleConflict("Snapshot hero identity mismatch")
            saved = state.combatants["hero"]
            if state.phase == "active" and (hero.current_health != saved.health or hero.current_mana != saved.mana):
                raise BattleConflict("Hero resources changed outside the combat engine")
        queued = list(battle.commands.filter(status="QUEUED").order_by("sequence")[:100])
        # A receipt is applied at this batch's starting boundary, never backdated.
        # Engine cursor prevents duplicate effects; stale queued receipts are rejected.
        inputs = []
        for command in queued:
            if command.sequence < 1 or command.sequence <= state.last_processed_command_sequence or type(command.payload) is not dict:
                command.status = "REJECTED"
                command.reject_reason = "stale_sequence" if command.sequence <= state.last_processed_command_sequence else "invalid_payload"
                command.processed_at = now
                command.save(update_fields=["status", "reject_reason", "processed_at"])
                continue
            inputs.append(BattleCommandInput(command.sequence, state.simulation_time_ms,
                                             command.command_type, command.payload))
        limited = False
        try:
            result = advance(snapshot, state, state.simulation_time_ms + elapsed_ms, tuple(inputs))
        except SimulationLimitReached as exc:
            result, limited = exc.result, True
        state = result.state
        BattleEvent.objects.bulk_create([BattleEvent(battle=battle, sequence=e.sequence,
            simulation_time_ms=e.simulation_time_ms, event_type=e.event_type,
            actor_id=e.actor_id, target_id=e.target_id, payload=e.payload) for e in result.events])
        by_sequence = {command.sequence: command for command in queued}
        for receipt in result.command_results:
            command = by_sequence[receipt.sequence]
            command.status = "ACCEPTED" if receipt.accepted else "REJECTED"
            command.reject_reason = receipt.reason
            command.execute_at_ms = inputs[0].execute_at_ms
            command.processed_at = now
            command.save(update_fields=["status", "reject_reason", "execute_at_ms", "processed_at"])
        battle.checkpoint = json.loads(state_to_json(snapshot, state))
        battle.last_event_sequence = state.last_event_sequence
        battle.last_processed_command_sequence = state.last_processed_command_sequence
        battle.outcome = state.outcome.result.upper() if state.outcome else None
        battle.status = "ACTIVE"
        battle.error_code = battle.error_message = None
        battle.next_due_at = now + timedelta(milliseconds=100)
        if state.outcome:
            _resolve(battle, hero, snapshot, state)
            battle.checkpoint = json.loads(state_to_json(snapshot, state))
            battle.last_event_sequence = state.last_event_sequence
            # Commands not in the bounded batch can never execute after completion.
            battle.commands.filter(status="QUEUED").update(status="REJECTED",
                reject_reason="battle_finished", processed_at=now)
        else:
            hero_state = state.combatants["hero"]
            if not _snapshot(hero).update(current_health=hero_state.health,
                    current_mana=hero_state.mana):
                raise BattleConflict("Hero changed during checkpoint commit")
            if limited:
                battle.status = "PAUSED_ERROR"
                battle.error_code = "simulation_limit"
                battle.error_message = "Battle exceeded ten minutes of simulation"
                battle.next_due_at = None
        battle.revision += 1
        battle.full_clean()
        fence(token)
        values = {field.name: getattr(battle, field.name) for field in Battle._meta.concrete_fields
                  if field.name not in {"id", "hero", "created_at"}}
        values["updated_at"] = timezone.now()
        if not Battle.objects.filter(pk=battle.pk, revision=revision).update(**values):
            raise BattleConflict("Battle revision changed")
        return battle.status


def pause_battle(battle_id, token, error):
    with transaction.atomic():
        fence(token)
        Battle.objects.filter(pk=battle_id, status__in=["PENDING", "ACTIVE", "RESOLVING"]).update(
            status="PAUSED_ERROR", error_code=type(error).__name__[:100],
            error_message=str(error), next_due_at=None, revision=F("revision") + 1,
            updated_at=timezone.now())


def retry_battle(battle_id, token):
    with transaction.atomic():
        fence(token)
        battle = Battle.objects.get(pk=battle_id, status="PAUSED_ERROR")
        if battle.error_code == "simulation_limit":
            raise ValueError("Simulation-limit battles require a rules decision, not automatic retry")
        if battle.checkpoint:
            battle.status = "RESOLVING" if battle.checkpoint.get("phase") == "finished" else "ACTIVE"
        else:
            battle.status = "PENDING"
        battle.error_code = battle.error_message = None
        battle.next_due_at = timezone.now()
        battle.revision += 1
        battle.save(update_fields=["status", "error_code", "error_message", "next_due_at", "revision", "updated_at"])
