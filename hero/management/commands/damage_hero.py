from django.core.management.base import BaseCommand
from hero.models import Hero
from hero.windows_tasks import damage_hero

class Command(BaseCommand):
    help = 'Damage a hero for testing healing system'

    def add_arguments(self, parser):
        parser.add_argument('hero_id', type=int, help='Hero ID to damage')
        parser.add_argument('damage', type=int, help='Amount of damage to deal')

    def handle(self, *args, **options):
        try:
            hero_id = options['hero_id']
            damage_amount = options['damage']

            # Use the Windows-compatible damage function
            if damage_hero(hero_id, damage_amount):
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully damaged hero {hero_id} for {damage_amount} HP'
                    )
                )
                self.stdout.write(
                    'Healing should start automatically via daemon.'
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f'Failed to damage hero {hero_id}')
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error: {e}')
            )