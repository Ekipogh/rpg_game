"""Dungeon transitions and optimistic persistence (including SQLite)."""
from copy import deepcopy
import random

from django.db import transaction
from django.db.models import F

from .encounters import ENCOUNTER_DEFINITIONS, Encounter
from .models import Hero


# Victories, rather than rooms visited, unlock the next gate.
REGULARS_PER_STAGE = 3


def battle_requirements(run=None, hero_level=1):
    run = run or {}
    victories = run.get('regular_victories', 0)
    miniboss = run.get('miniboss_defeated', False)
    tier = ('boss' if miniboss else 'miniboss') if victories >= REGULARS_PER_STAGE else 'enemy'
    progress = victories + (REGULARS_PER_STAGE + 1 if miniboss else 0)
    target = max(1, hero_level) + progress // 2
    group_limit = min(3, 2 + progress // 2)
    return tier, target, group_limit


def available_encounter_keys(hero_level=1, run=None):
    """Filter complete configured groups; never change their authored monsters."""
    from battle.models import EncounterMonster

    groups = {}
    for entry in EncounterMonster.objects.select_related('monster').order_by('pk'):
        groups.setdefault(entry.encounter_definition_key, []).append(entry)
    tier, target, group_limit = battle_requirements(run, hero_level or 1)
    configured = set()
    for key, entries in groups.items():
        definition = ENCOUNTER_DEFINITIONS.get(key)
        if definition is None or definition.kind != 'battle':
            continue
        count = sum(entry.quantity for entry in entries)
        if not 1 <= count <= 3:
            continue
        if hero_level is not None:
            threats = [entry.monster.threat_level for entry in entries for _ in range(entry.quantity)]
            expected = 'common' if tier == 'enemy' else tier
            if definition.battle_tier != tier or threats.count(expected) < 1:
                continue
            if any(t != 'common' and t != expected for t in threats):
                continue
            if tier != 'enemy' and threats.count(expected) != 1:
                continue
            if count > group_limit or any(not max(1, target - 2) <= e.monster.level <= target + 1
                                          for e in entries):
                continue
            if sum(e.monster.level * e.quantity for e in entries) > target * group_limit:
                continue
        configured.add(key)
    # A gate cannot be bypassed by selecting a peaceful room when its fight exists.
    if hero_level is not None and tier != 'enemy' and configured:
        return tuple(key for key in ENCOUNTER_DEFINITIONS if key in configured)
    return tuple(key for key, definition in ENCOUNTER_DEFINITIONS.items()
                 if definition.kind != 'battle' or key in configured)


def create_run(hero_level=1):
    return {
        'current_floor': 1,
        'current_encounter': Encounter.create(random.choice(available_encounter_keys(hero_level)), 1).to_dict(),
        'phase': 'encounter', 'last_result': None,
        'path_left': None, 'path_right': None,
        'hero_level': hero_level or 1, 'regular_victories': 0, 'miniboss_defeated': False,
    }


def generate_paths(floor, hero_level=1, run=None):
    if run is not None:
        hero_level = run.get('hero_level', hero_level or 1)
    options = available_encounter_keys(hero_level, run)
    return {side: Encounter.create(random.choice(options), floor).to_dict()
            for side in ('path_left', 'path_right')}


def resolve_encounter(run, health, max_health, experience):
    """Return (run, health, experience) without mutating the input or saving."""
    if run['phase'] != 'encounter':
        raise ValueError('No encounter to resolve.')
    run = deepcopy(run)
    encounter = Encounter.from_dict(run['current_encounter'])
    floor = run['current_floor']
    if encounter.floor != floor:
        raise ValueError('Encounter floor mismatch.')
    old_health, old_xp = health, experience
    if encounter.kind == 'battle':
        raise ValueError('Battles are resolved by the combat engine.')
    elif encounter.kind == 'trap':
        health -= random.randint(3, 8) * floor
    elif encounter.kind == 'treasure':
        experience += 10 * floor
    elif encounter.kind == 'npc':
        health = min(max_health, health + 5)
    health = max(0, health)
    result = {'health_change': health - old_health, 'experience_change': experience - old_xp,
              'survived': health > 0, 'title': encounter.definition.title, 'loot': []}
    if health == 0:
        return {}, 1, experience
    run['last_result'] = result
    run['phase'] = 'choices'
    run.update(generate_paths(floor + 1, run=run))
    return run, health, experience


def choose_path(run, index):
    """Select a saved path without mutating the input."""
    if run['phase'] != 'choices' or type(index) is not int or index not in (0, 1):
        raise ValueError('Invalid path selection.')
    run = deepcopy(run)
    encounter = Encounter.from_dict(run['path_left' if index == 0 else 'path_right'])
    if encounter.floor != run['current_floor'] + 1:
        raise ValueError('Path floor mismatch.')
    run.update(current_floor=encounter.floor, current_encounter=encounter.to_dict(),
               phase='encounter', path_left=None, path_right=None)
    return run


def _snapshot(hero):
    # Compare every input to the calculation, plus JSON state, before writing.
    fields = ('dungeon_revision', 'dungeon_run', 'current_health', 'max_health',
              'current_mana', 'max_mana', 'experience', 'is_in_combat')
    return Hero.objects.filter(pk=hero.pk, **{field: getattr(hero, field) for field in fields})


def enter_or_resume(hero_id):
    hero = Hero.objects.filter(pk=hero_id).first()
    if hero is None:
        return 'invalid'
    if hero.dungeon_run:
        with transaction.atomic():
            ensure_battle(hero)
        return 'success'
    if hero.not_healed:
        return 'not_healed'
    with transaction.atomic():
        updated = _snapshot(hero).update(dungeon_run=create_run(hero.level), is_in_combat=True,
                                         dungeon_revision=F('dungeon_revision') + 1)
        if updated:
            hero.refresh_from_db()
            ensure_battle(hero)
    return 'success' if updated else 'stale'


def apply_action(hero_id, action, expected_revision, choice=None):
    """Return success/stale/invalid, or retreat/defeat after an accepted exit."""
    hero = Hero.objects.filter(pk=hero_id).first()
    if hero is None or type(expected_revision) is not int:
        return 'invalid'
    if hero.dungeon_revision != expected_revision:
        return 'stale'
    run, health, xp = hero.dungeon_run, hero.current_health, hero.experience
    if not run:
        return 'invalid'
    outcome = 'success'
    try:
        if action == 'resolve' and choice is None:
            run = deepcopy(run)
            run['hero_level'] = hero.level
            run, health, xp = resolve_encounter(run, health, hero.max_health, xp)
            if not run:
                outcome = 'defeat'
        elif action == 'choose':
            run = choose_path(run, choice)
        elif action == 'retreat' and run['phase'] == 'choices' and choice is None:
            run, outcome = {}, 'retreat'
        else:
            return 'invalid'
    except (ValueError, KeyError, TypeError):
        return 'invalid'
    with transaction.atomic():
        updated = _snapshot(hero).update(
            dungeon_run=run, current_health=health, experience=xp, is_in_combat=bool(run),
            dungeon_revision=F('dungeon_revision') + 1)
        if updated:
            hero.refresh_from_db()
            ensure_battle(hero)
    return outcome if updated else 'stale'


def ensure_battle(hero):
    """Called inside accepted transition transactions; GET never creates a fight."""
    from battle.models import Battle
    run = hero.dungeon_run
    if not run or run['phase'] != 'encounter':
        return None
    encounter = Encounter.from_dict(run['current_encounter'])
    if encounter.kind != 'battle':
        return None
    battle, _ = Battle.objects.get_or_create(encounter_id=encounter.id, defaults={'hero': hero})
    if battle.hero_id != hero.pk:
        raise ValueError('Encounter belongs to another hero.')
    return battle
