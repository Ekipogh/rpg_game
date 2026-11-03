"""Dungeon transitions and optimistic persistence (including SQLite)."""
from copy import deepcopy
import random

from django.db.models import F

from .encounters import ENCOUNTER_DEFINITIONS, Encounter
from .models import Hero


def create_run():
    return {
        'current_floor': 1,
        'current_encounter': Encounter.create('goblin_ambush', 1).to_dict(),
        'phase': 'encounter', 'last_result': None,
        'path_left': None, 'path_right': None,
    }


def generate_paths(floor):
    return {side: Encounter.create(random.choice(tuple(ENCOUNTER_DEFINITIONS)), floor).to_dict()
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
    ranges = {'enemy': (5, 10), 'miniboss': (10, 15), 'boss': (15, 20)}
    if encounter.kind == 'battle':
        health -= random.randint(*ranges[encounter.battle_tier]) * floor
    elif encounter.kind == 'trap':
        health -= random.randint(3, 8) * floor
    elif encounter.kind == 'treasure':
        experience += 10 * floor
    elif encounter.kind == 'npc':
        health = min(max_health, health + 5)
    health = max(0, health)
    result = {'health_change': health - old_health, 'experience_change': experience - old_xp,
              'survived': health > 0, 'title': encounter.definition.title}
    if health == 0:
        return {}, 1, experience
    run['last_result'] = result
    run['phase'] = 'choices'
    run.update(generate_paths(floor + 1))
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
    if hero.not_healed:
        return 'not_healed'
    if hero.dungeon_run:
        return 'success'
    updated = _snapshot(hero).update(dungeon_run=create_run(), is_in_combat=True,
                                     dungeon_revision=F('dungeon_revision') + 1)
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
    updated = _snapshot(hero).update(
        dungeon_run=run, current_health=health, experience=xp, is_in_combat=bool(run),
        dungeon_revision=F('dungeon_revision') + 1)
    return outcome if updated else 'stale'
