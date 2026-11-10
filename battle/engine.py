"""Deterministic combat engine. No persistence or wall-clock dependencies.

Version identifiers cover scheduling, formulas, serialization, and RNG behavior.
Commit AdvanceResult state, events, and command receipts as one persistence unit.
"""

from dataclasses import dataclass, asdict, fields
from copy import deepcopy
import hashlib
import json
from typing import get_type_hints, get_origin, get_args
import types
from typing import Literal

SCHEMA_VERSION = 1
RULES_VERSION = "ranged-v1"
RNG_VERSION = "sha256-counter-v1"

Team = Literal["hero", "enemy"]
MovementPolicy = Literal["approach", "hold"]

""" Snapshot Section """


@dataclass(frozen=True)
class CombatStats:
    max_health: int
    max_mana: int

    attack: int
    defense: int
    magic: int
    magic_defense: int
    speed: int

    accuracy: int
    evasion: int
    critical_chance: int
    critical_damage_bp: int  # 15000 = 1.5x


@dataclass(frozen=True)
class LootEntry:
    item_id: int
    drop_chance_bp: int  # 10000 = 100% chance
    min_quantity: int
    max_quantity: int


@dataclass(frozen=True)
class RewardSnapshot:
    experience: int
    loot: tuple[LootEntry, ...]


@dataclass(frozen=True)
class CombatantSnapshot:
    combatant_id: str  # "hero" "enemy:0" "enemy:1"
    team: Team

    source_type: Literal["hero", "monster"]
    source_id: int  # Reference for audit; engine does not query it
    name: str

    stats: CombatStats
    attack_range_min: int
    attack_range_max: int

    initial_health: int
    initial_mana: int
    initial_lane: int
    initial_movement_policy: MovementPolicy

    rewards: RewardSnapshot | None  # Enemies only


@dataclass(frozen=True)
class BattleRules:
    lane_count: int
    movement_interval_ms: int
    max_simulation_ms: int
    attack_interval_min_ms: int
    attack_interval_base_ms: int
    speed_divisor: int


@dataclass(frozen=True)
class BattleSnapshot:
    schema_version: int
    rules_version: str
    rng_version: str

    battle_id: str
    encounter_id: str
    encounter_definition_key: str
    floor: int
    battle_tier: Literal["enemy", "miniboss", "boss"]

    rules: BattleRules
    combatants: tuple[CombatantSnapshot, ...]
    initial_rng_seed: str


""" Snapshot Section End """

""" State Section """


@dataclass
class CombatantState:
    combatant_id: str

    health: int
    mana: int
    lane: int

    movement_policy: MovementPolicy
    selected_target_id: str | None  # Manual override
    current_target_id: str | None  # Engine selected target

    next_attack_at_ms: int | None
    next_movement_at_ms: int | None


@dataclass
class RngState:
    seed: str
    counter: int


@dataclass
class LootDrop:
    enemy_id: str
    item_id: int
    quantity: int


@dataclass
class BattleOutcome:
    result: Literal["victory", "defeat"]
    finished_at_ms: int
    experience: int
    loot: tuple[LootDrop, ...]


@dataclass
class BattleState:
    schema_version: int
    battle_id: str

    phase: Literal["active", "finished"]
    simulation_time_ms: int

    combatants: dict[str, CombatantState]
    rng: RngState

    last_event_sequence: int
    last_processed_command_sequence: int

    outcome: BattleOutcome | None


""" State Section End """


@dataclass(frozen=True)
class BattleCommandInput:
    sequence: int
    execute_at_ms: int
    command_type: Literal["select_target", "set_movement_policy"]
    payload: dict


@dataclass(frozen=True)
class CombatEvent:
    sequence: int
    simulation_time_ms: int
    event_type: str
    actor_id: str | None
    target_id: str | None
    payload: dict


@dataclass(frozen=True)
class CommandResult:
    sequence: int
    accepted: bool
    reason: str | None = None


@dataclass(frozen=True)
class AdvanceResult:
    state: BattleState
    events: tuple[CombatEvent, ...]
    command_results: tuple[CommandResult, ...]


class SimulationLimitReached(RuntimeError):
    def __init__(self, result: AdvanceResult):
        super().__init__("Battle reached its simulation limit")
        self.result = result


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def validate_snapshot(snapshot: BattleSnapshot):
    if not isinstance(snapshot, BattleSnapshot):
        raise ValueError("Expected BattleSnapshot")
    # Also enforce annotated shapes for callers constructing dataclasses directly.
    _decode(BattleSnapshot, asdict(snapshot))
    if (snapshot.schema_version != SCHEMA_VERSION or
            snapshot.rules_version not in ("melee-v1", RULES_VERSION) or snapshot.rng_version != RNG_VERSION):
        raise ValueError("Unsupported snapshot version")
    for name in ("battle_id", "encounter_id", "encounter_definition_key", "initial_rng_seed"):
        if not getattr(snapshot, name).strip():
            raise ValueError(f"Empty {name}")
    _integer(snapshot.floor, "floor", 1)
    for field in fields(snapshot.rules):
        _integer(getattr(snapshot.rules, field.name), field.name, 1)
    if snapshot.rules.lane_count < 2:
        raise ValueError("At least two lanes required")
    if not isinstance(snapshot.combatants, tuple):
        raise ValueError("Snapshot combatants must be a tuple")
    ids, lanes = set(), set()
    heroes = enemies = 0
    for actor in snapshot.combatants:
        if not actor.combatant_id.strip() or actor.combatant_id in ids:
            raise ValueError("Combatant IDs must be unique and nonempty")
        ids.add(actor.combatant_id)
        heroes += actor.team == "hero"
        enemies += actor.team == "enemy"
        if actor.source_type != ("hero" if actor.team == "hero" else "monster"):
            raise ValueError("Source type does not match team")
        _integer(actor.source_id, "source_id", 1)
        for field in fields(actor.stats):
            value = getattr(actor.stats, field.name)
            if field.name == "speed":
                if type(value) is not int:
                    raise ValueError("speed must be an integer")
            else:
                _integer(value, field.name, 1 if field.name == "max_health" else 0)
        _integer(actor.attack_range_min, "attack_range_min", 1)
        _integer(actor.attack_range_max, "attack_range_max", actor.attack_range_min)
        if actor.attack_range_max >= snapshot.rules.lane_count:
            raise ValueError("Attack range exceeds battlefield")
        if snapshot.rules_version == "melee-v1" and (actor.attack_range_min, actor.attack_range_max) != (1, 1):
            raise ValueError("Legacy battles only support melee range 1")
        if actor.initial_movement_policy not in ("approach", "hold"):
            raise ValueError("Unsupported movement policy")
        _integer(actor.initial_health, "initial_health", 1)
        _integer(actor.initial_mana, "initial_mana")
        _integer(actor.initial_lane, "initial_lane")
        if (actor.initial_health > actor.stats.max_health or
                actor.initial_mana > actor.stats.max_mana or
                actor.initial_lane >= snapshot.rules.lane_count or actor.initial_lane in lanes):
            raise ValueError("Invalid initial resources or occupied lane")
        lanes.add(actor.initial_lane)
        if actor.team == "hero" and actor.rewards is not None:
            raise ValueError("Heroes cannot grant rewards")
        if actor.rewards is not None:
            _integer(actor.rewards.experience, "experience")
            if not isinstance(actor.rewards.loot, tuple):
                raise ValueError("Loot table must be a tuple")
            for entry in actor.rewards.loot:
                _integer(entry.item_id, "item_id", 1)
                _integer(entry.drop_chance_bp, "drop_chance_bp")
                _integer(entry.min_quantity, "min_quantity", 1)
                _integer(entry.max_quantity, "max_quantity", entry.min_quantity)
                if entry.drop_chance_bp > 10000:
                    raise ValueError("Drop probability exceeds 100%")
    if heroes != 1 or not 1 <= enemies <= 3:
        raise ValueError("Expected one hero and one to three enemies")


def validate_state(snapshot: BattleSnapshot, state: BattleState):
    validate_snapshot(snapshot)
    if not isinstance(state, BattleState):
        raise ValueError("Expected BattleState")
    _decode(BattleState, asdict(state))
    if state.schema_version != SCHEMA_VERSION or state.battle_id != snapshot.battle_id:
        raise ValueError("Checkpoint version or identity mismatch")
    _integer(state.simulation_time_ms, "simulation_time_ms")
    if state.simulation_time_ms > snapshot.rules.max_simulation_ms:
        raise ValueError("Checkpoint exceeds simulation limit")
    _integer(state.last_event_sequence, "last_event_sequence")
    _integer(state.last_processed_command_sequence, "last_processed_command_sequence")
    _integer(state.rng.counter, "rng counter")
    if state.rng.seed != snapshot.initial_rng_seed:
        raise ValueError("RNG seed mismatch")
    definitions = {c.combatant_id: c for c in snapshot.combatants}
    if set(definitions) != set(state.combatants):
        raise ValueError("Checkpoint combatants do not match snapshot")
    lanes = set()
    for key, actor in state.combatants.items():
        definition = definitions[key]
        if key != actor.combatant_id or actor.movement_policy not in ("approach", "hold"):
            raise ValueError("Invalid combatant identity or policy")
        for name, maximum in (("health", definition.stats.max_health),
                              ("mana", definition.stats.max_mana),
                              ("lane", snapshot.rules.lane_count - 1)):
            _integer(getattr(actor, name), name)
            if getattr(actor, name) > maximum:
                raise ValueError(f"Invalid {name}")
        if actor.health:
            if actor.lane in lanes:
                raise ValueError("Living combatants share a lane")
            lanes.add(actor.lane)
        for timer in (actor.next_attack_at_ms, actor.next_movement_at_ms):
            if actor.health and state.phase == "active":
                _integer(timer, "action timer", state.simulation_time_ms + 1)
            elif timer is not None:
                raise ValueError("Dead or finished combatants cannot have timers")
        for target in (actor.selected_target_id, actor.current_target_id):
            if target is not None and (target not in definitions or
                    definitions[target].team == definition.team or
                    not state.combatants[target].health):
                raise ValueError("Invalid target")
    hero_alive = any(c.team == "hero" and state.combatants[c.combatant_id].health
                     for c in snapshot.combatants)
    enemies_alive = any(c.team == "enemy" and state.combatants[c.combatant_id].health
                        for c in snapshot.combatants)
    if state.phase == "active":
        if state.outcome is not None or not hero_alive or not enemies_alive:
            raise ValueError("Active checkpoint has terminal outcome")
    else:
        outcome = state.outcome
        if outcome is None or (hero_alive and enemies_alive):
            raise ValueError("Invalid finished checkpoint")
        expected = "victory" if hero_alive else "defeat"
        if outcome.result != expected or outcome.finished_at_ms != state.simulation_time_ms:
            raise ValueError("Outcome does not match checkpoint")
        _integer(outcome.experience, "outcome experience")
        if not isinstance(outcome.loot, tuple):
            raise ValueError("Outcome loot must be a tuple")
        if expected == "defeat" and (outcome.experience or outcome.loot):
            raise ValueError("Defeat cannot grant rewards")
        expected_xp = sum(c.rewards.experience for c in snapshot.combatants if c.rewards)
        if expected == "victory" and outcome.experience != expected_xp:
            raise ValueError("Incorrect victory experience")
        available_entries = {c.combatant_id: list(c.rewards.loot)
                             for c in snapshot.combatants if c.rewards}
        for drop in outcome.loot:
            _integer(drop.item_id, "loot item", 1)
            _integer(drop.quantity, "loot quantity", 1)
            source = definitions.get(drop.enemy_id)
            entries = available_entries.get(drop.enemy_id, [])
            match = next((e for e in entries if e.item_id == drop.item_id and
                          e.drop_chance_bp > 0 and e.min_quantity <= drop.quantity <= e.max_quantity), None)
            if source is None or source.team != "enemy" or match is None:
                raise ValueError("Invalid loot outcome")
            entries.remove(match)


def attack_interval_ms(stats: CombatStats, rules: BattleRules) -> int:
    denominator = rules.speed_divisor + max(0, stats.speed)
    return max(rules.attack_interval_min_ms,
               (rules.attack_interval_base_ms * rules.speed_divisor + denominator - 1) // denominator)


def random_integer(rng: RngState, minimum: int, maximum: int) -> int:
    """SHA-256(seed byte length || seed || counter), unbiased inclusive bounds."""
    _integer(rng.counter, "rng counter")
    if type(minimum) is not int or type(maximum) is not int or minimum > maximum:
        raise ValueError("Invalid random bounds")
    width = maximum - minimum + 1
    if width > 2**256:
        raise ValueError("Random range exceeds 256 bits")
    seed = rng.seed.encode("utf-8")
    limit = 2**256 - (2**256 % width)
    while True:
        data = str(len(seed)).encode("ascii") + b":" + seed + b":" + str(rng.counter).encode("ascii")
        value = int.from_bytes(hashlib.sha256(data).digest(), "big")
        rng.counter += 1
        if value < limit:
            return minimum + value % width


def create_battle(snapshot: BattleSnapshot) -> BattleState:
    validate_snapshot(snapshot)
    return BattleState(SCHEMA_VERSION, snapshot.battle_id, "active", 0, {
        c.combatant_id: CombatantState(c.combatant_id, c.initial_health, c.initial_mana,
            c.initial_lane, c.initial_movement_policy, None, None,
            attack_interval_ms(c.stats, snapshot.rules), snapshot.rules.movement_interval_ms)
        for c in snapshot.combatants
    }, RngState(snapshot.initial_rng_seed, 0), 0, 0, None)


def advance(snapshot: BattleSnapshot, state: BattleState, until_simulation_ms: int,
            commands: tuple[BattleCommandInput, ...] = ()) -> AdvanceResult:
    """Advance a copy; callers persist the returned checkpoint and events atomically.

    Supply only commands due by the requested time, ordered by receipt sequence
    with nondecreasing execution timestamps. Sequences at/below the checkpoint's
    command cursor are duplicate deliveries and are ignored.
    """
    validate_state(snapshot, state)
    _integer(until_simulation_ms, "until_simulation_ms", state.simulation_time_ms)
    pending = []
    previous_sequence = state.last_processed_command_sequence
    previous_time = state.simulation_time_ms
    for command in commands:
        if not isinstance(command, BattleCommandInput):
            raise ValueError("Expected BattleCommandInput")
        _integer(command.sequence, "command sequence", 1)
        _integer(command.execute_at_ms, "command timestamp")
        if command.sequence <= state.last_processed_command_sequence:
            continue
        if command.sequence <= previous_sequence or not previous_time <= command.execute_at_ms <= until_simulation_ms:
            raise ValueError("Commands must have increasing sequences and ordered due timestamps")
        if type(command.payload) is not dict or type(command.command_type) is not str:
            raise ValueError("Malformed command")
        pending.append(command)
        previous_sequence, previous_time = command.sequence, command.execute_at_ms
    state = deepcopy(state)
    definitions = {c.combatant_id: c for c in snapshot.combatants}
    actors = [state.combatants[key] for key in sorted(state.combatants)]
    events, results = [], []

    def emit(kind, actor=None, target=None, **payload):
        state.last_event_sequence += 1
        events.append(CombatEvent(state.last_event_sequence, state.simulation_time_ms,
                                  kind, actor, target, payload))

    def reachable(actor, target):
        if target.health <= 0 or definitions[actor.combatant_id].team == definitions[target.combatant_id].team:
            return False
        # Ranged shots can pass other combatants; melee cannot bypass a front line.
        return definitions[actor.combatant_id].attack_range_max > 1 or not any(
            c.health and min(actor.lane, target.lane) < c.lane < max(actor.lane, target.lane)
            for c in actors)

    def target_for(actor):
        if not actor.health:
            actor.selected_target_id = None
            target = None
        else:
            target = state.combatants.get(actor.selected_target_id)
            if target is None or not reachable(actor, target):
                actor.selected_target_id = None
                candidates = [c for c in actors if reachable(actor, c)]
                target = min(candidates, key=lambda c: (abs(c.lane - actor.lane), c.combatant_id), default=None)
        target_id = target.combatant_id if target else None
        if actor.current_target_id != target_id:
            actor.current_target_id = target_id
            emit("target_change", actor.combatant_id, target_id)
        return target

    def finish_if_needed():
        hero_alive = any(c.health and definitions[c.combatant_id].team == "hero" for c in actors)
        enemy_alive = any(c.health and definitions[c.combatant_id].team == "enemy" for c in actors)
        if hero_alive and enemy_alive:
            return
        xp, drops = 0, []
        if hero_alive:
            for key in sorted(definitions):
                reward = definitions[key].rewards
                if reward:
                    xp += reward.experience
                    for entry in reward.loot:
                        if random_integer(state.rng, 0, 9999) < entry.drop_chance_bp:
                            drops.append(LootDrop(key, entry.item_id,
                                random_integer(state.rng, entry.min_quantity, entry.max_quantity)))
        state.phase = "finished"
        state.outcome = BattleOutcome("victory" if hero_alive else "defeat",
                                     state.simulation_time_ms, xp, tuple(drops))
        for actor in actors:
            actor.next_attack_at_ms = actor.next_movement_at_ms = None
        emit("battle_complete", result=state.outcome.result, experience=xp,
             loot=[asdict(drop) for drop in drops])

    def execute(command):
        reason = None
        hero = next(c for c in actors if definitions[c.combatant_id].team == "hero")
        if state.phase == "finished":
            reason = "battle_finished"
        elif command.command_type == "select_target" and set(command.payload) == {"target_id"}:
            key = command.payload["target_id"]
            target = state.combatants.get(key) if isinstance(key, str) else None
            if target is None or not reachable(hero, target):
                reason = "invalid_target"
            else:
                hero.selected_target_id = key
        elif command.command_type == "set_movement_policy" and set(command.payload) == {"policy"}:
            policy = command.payload["policy"]
            if policy not in ("approach", "hold"):
                reason = "unsupported_policy"
            else:
                hero.movement_policy = policy
        else:
            reason = "invalid_command"
        results.append(CommandResult(command.sequence, reason is None, reason))
        state.last_processed_command_sequence = command.sequence

    index = 0
    end = min(until_simulation_ms, snapshot.rules.max_simulation_ms)
    while state.phase == "active":
        due = [timer for c in actors for timer in (c.next_attack_at_ms, c.next_movement_at_ms) if timer is not None]
        if index < len(pending):
            due.append(pending[index].execute_at_ms)
        timestamp = min(due)
        if timestamp > end:
            state.simulation_time_ms = end
            break
        state.simulation_time_ms = timestamp
        while index < len(pending) and pending[index].execute_at_ms == timestamp:
            execute(pending[index])
            index += 1
        for actor in actors:
            target_for(actor)
        for actor in actors:
            if actor.next_movement_at_ms != timestamp:
                continue
            actor.next_movement_at_ms = timestamp + snapshot.rules.movement_interval_ms
            target = target_for(actor)
            definition = definitions[actor.combatant_id]
            distance = abs(actor.lane - target.lane) if target else 0
            if target and actor.movement_policy == "approach" and not definition.attack_range_min <= distance <= definition.attack_range_max:
                direction = 1 if target.lane > actor.lane else -1
                lane = actor.lane + (direction if distance > definition.attack_range_max else -direction)
                if 0 <= lane < snapshot.rules.lane_count and not any(c.health and c.lane == lane for c in actors):
                    old_lane, actor.lane = actor.lane, lane
                    emit("move", actor.combatant_id, from_lane=old_lane, to_lane=lane)
        for actor in actors:
            if actor.next_attack_at_ms != timestamp:
                continue
            definition = definitions[actor.combatant_id]
            actor.next_attack_at_ms = timestamp + attack_interval_ms(definition.stats, snapshot.rules)
            target = target_for(actor)
            if target is None or not definition.attack_range_min <= abs(actor.lane - target.lane) <= definition.attack_range_max:
                continue
            attack, defense = definition.stats, definitions[target.combatant_id].stats
            emit("attack", actor.combatant_id, target.combatant_id,
                 **({"ranged": True} if definition.attack_range_max > 1 else {}))
            if random_integer(state.rng, 0, 9999) >= max(5, min(100, attack.accuracy - defense.evasion)) * 100:
                emit("miss", actor.combatant_id, target.combatant_id)
                continue
            critical = random_integer(state.rng, 0, 9999) < max(0, min(100, attack.critical_chance)) * 100
            multiplier = attack.critical_damage_bp if critical else 10000
            damage = max(1, (max(2, 2 * attack.attack - defense.defense) * multiplier + 10000) // 20000)
            if critical:
                emit("critical", actor.combatant_id, target.combatant_id, damage=damage)
            applied = min(target.health, damage)
            target.health -= applied
            emit("damage", actor.combatant_id, target.combatant_id, damage=damage,
                 applied=applied, health=target.health, critical=critical)
            if not target.health:
                target.next_attack_at_ms = target.next_movement_at_ms = None
                emit("defeat", target.combatant_id)
                for other in actors:
                    target_for(other)
                finish_if_needed()
                if state.phase == "finished":
                    break
        if state.simulation_time_ms == end:
            break
    # Commands after an early finish are rejected without advancing terminal time.
    if state.phase == "finished":
        for command in pending[index:]:
            execute(command)
    result = AdvanceResult(state, tuple(events), tuple(results))
    validate_state(snapshot, state)
    if state.phase == "active" and state.simulation_time_ms == snapshot.rules.max_simulation_ms:
        raise SimulationLimitReached(result)
    return result


def _decode(cls, value):
    """Strict JSON-shaped reconstruction, including nested dataclasses."""
    origin, args = get_origin(cls), get_args(cls)
    if origin in (types.UnionType,):
        for option in args:
            try:
                return _decode(option, value)
            except ValueError:
                pass
        raise ValueError("Invalid optional value")
    if origin is Literal:
        if not any(type(value) is type(option) and value == option for option in args):
            raise ValueError("Invalid literal")
        return value
    if origin is tuple:
        if not isinstance(value, (list, tuple)):
            raise ValueError("Expected array")
        return tuple(_decode(args[0], item) for item in value)
    if origin is dict:
        if type(value) is not dict:
            raise ValueError("Expected object")
        return {_decode(args[0], k): _decode(args[1], v) for k, v in value.items()}
    if hasattr(cls, "__dataclass_fields__"):
        if type(value) is not dict or set(value) != {f.name for f in fields(cls)}:
            raise ValueError("Unexpected or missing fields")
        hints = get_type_hints(cls)
        return cls(**{name: _decode(hints[name], item) for name, item in value.items()})
    if type(value) is not cls:
        raise ValueError(f"Expected {cls}")
    return value


def snapshot_to_json(snapshot: BattleSnapshot) -> str:
    validate_snapshot(snapshot)
    return json.dumps(asdict(snapshot), sort_keys=True, separators=(",", ":"))


def snapshot_from_json(data: str) -> BattleSnapshot:
    snapshot = _decode(BattleSnapshot, json.loads(data))
    validate_snapshot(snapshot)
    return snapshot


def state_to_json(snapshot: BattleSnapshot, state: BattleState) -> str:
    validate_state(snapshot, state)
    return json.dumps(asdict(state), sort_keys=True, separators=(",", ":"))


def state_from_json(snapshot: BattleSnapshot, data: str) -> BattleState:
    state = _decode(BattleState, json.loads(data))
    validate_state(snapshot, state)
    return state
