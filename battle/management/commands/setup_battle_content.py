"""Create editable starter compositions without overwriting existing content."""
from django.core.management.base import BaseCommand
from django.db import transaction
from hero.models import Monster
from battle.models import EncounterMonster


class Command(BaseCommand):
    help = "Create missing starter monster templates and encounter compositions."

    @transaction.atomic
    def handle(self, *args, **options):
        entries = (
            ('goblin_ambush', 'Goblin', 'common', 30, 8, 2, 10, 10),
            ('ogre_guard', 'Ogre guard', 'miniboss', 80, 14, 5, 5, 30),
            ('dungeon_guardian', 'Dungeon guardian', 'boss', 150, 18, 8, 15, 75),
        )
        for key, name, tier, hp, attack, defense, speed, xp in entries:
            if EncounterMonster.objects.filter(encounter_definition_key=key).exists():
                self.stdout.write(f'{key}: existing composition retained')
                continue
            monster, _ = Monster.objects.get_or_create(name=name, defaults={
                'threat_level': tier, 'max_health': hp, 'current_health': hp,
                'attack': attack, 'defense': defense, 'speed': speed, 'experience_reward': xp,
            })
            entry = EncounterMonster(encounter_definition_key=key, monster=monster)
            entry.full_clean()
            entry.save()
            self.stdout.write(self.style.SUCCESS(f'{key}: configured {name}'))
