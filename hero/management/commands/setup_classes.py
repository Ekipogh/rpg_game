"""
Management command to set up hero classes with proper stat growth according to BATTLE_SYSTEM.md
"""
from django.core.management.base import BaseCommand
from hero.models import HeroClass


class Command(BaseCommand):
    help = 'Set up hero classes with stat growth values'

    def handle(self, *args, **options):
        # Warrior: High ATK and HP, moderate DEF and SPD, low MAG/MDEF/MP
        warrior, created = HeroClass.objects.update_or_create(
            name="Warrior",
            defaults={
                'description': 'A mighty warrior with high physical power and endurance.',
                'base_health': 120,
                'base_mana': 30,
                'base_attack': 15,
                'base_defense': 12,
                'base_magic': 5,
                'base_magic_defense': 8,
                'base_speed': 10,
                # Stat growth per level
                'atk_gain_min': 2,
                'atk_gain_max': 3,
                'def_gain_min': 1,
                'def_gain_max': 2,
                'mag_gain_min': 0,
                'mag_gain_max': 1,
                'mdef_gain_min': 0,
                'mdef_gain_max': 1,
                'spd_gain_min': 1,
                'spd_gain_max': 2,
                'hp_gain_min': 8,
                'hp_gain_max': 12,
                'mp_gain_min': 0,
                'mp_gain_max': 3,
            }
        )
        self.stdout.write(self.style.SUCCESS(f'{"Created" if created else "Updated"} Warrior class'))

        # Ranger: Balanced physical stats with high SPD
        ranger, created = HeroClass.objects.update_or_create(
            name="Ranger",
            defaults={
                'description': 'A swift and agile ranger, master of ranged combat.',
                'base_health': 100,
                'base_mana': 50,
                'base_attack': 12,
                'base_defense': 10,
                'base_magic': 8,
                'base_magic_defense': 10,
                'base_speed': 14,
                # Stat growth per level
                'atk_gain_min': 1,
                'atk_gain_max': 2,
                'def_gain_min': 1,
                'def_gain_max': 2,
                'mag_gain_min': 0,
                'mag_gain_max': 2,
                'mdef_gain_min': 1,
                'mdef_gain_max': 2,
                'spd_gain_min': 2,
                'spd_gain_max': 3,
                'hp_gain_min': 5,
                'hp_gain_max': 8,
                'mp_gain_min': 2,
                'mp_gain_max': 5,
            }
        )
        self.stdout.write(self.style.SUCCESS(f'{"Created" if created else "Updated"} Ranger class'))

        # Wizard: High MAG and MP, low physical stats
        wizard, created = HeroClass.objects.update_or_create(
            name="Wizard",
            defaults={
                'description': 'A powerful spellcaster with mastery over arcane magic.',
                'base_health': 80,
                'base_mana': 100,
                'base_attack': 6,
                'base_defense': 8,
                'base_magic': 16,
                'base_magic_defense': 14,
                'base_speed': 9,
                # Stat growth per level
                'atk_gain_min': 0,
                'atk_gain_max': 1,
                'def_gain_min': 0,
                'def_gain_max': 1,
                'mag_gain_min': 2,
                'mag_gain_max': 4,
                'mdef_gain_min': 1,
                'mdef_gain_max': 3,
                'spd_gain_min': 0,
                'spd_gain_max': 2,
                'hp_gain_min': 3,
                'hp_gain_max': 6,
                'mp_gain_min': 5,
                'mp_gain_max': 10,
            }
        )
        self.stdout.write(self.style.SUCCESS(f'{"Created" if created else "Updated"} Wizard class'))

        self.stdout.write(self.style.SUCCESS('Hero classes setup complete!'))
