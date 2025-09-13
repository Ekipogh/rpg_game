"""
Management command to populate the database with sample items
Usage: python manage.py populate_items
"""
from django.core.management.base import BaseCommand
from item.models import Item, Weapon, Armor, Consumable, OffHand


class Command(BaseCommand):
    help = 'Populate the database with sample items for testing'

    def handle(self, *args, **options):
        self.stdout.write('Creating sample items...')

        # Clear existing items
        Item.objects.all().delete()

        # Create weapons
        weapons_data = [
            {
                'name': 'Iron Sword',
                'description': 'A sturdy iron blade perfect for beginners',
                'value': 100,
                'damage': 25,
                'weapon_type': 'sword',
                'equipment_slot': 'weapon'
            },
            {
                'name': 'Steel Axe',
                'description': 'A heavy steel axe that cleaves through enemies',
                'value': 200,
                'damage': 35,
                'weapon_type': 'axe',
                'equipment_slot': 'weapon'
            },
            {
                'name': 'Dragon Slayer',
                'description': 'A legendary sword forged from dragon scales',
                'value': 1000,
                'damage': 75,
                'weapon_type': 'sword',
                'equipment_slot': 'weapon'
            },
            {
                'name': 'Elven Bow',
                'description': 'An elegant bow crafted by elven artisans',
                'value': 300,
                'damage': 40,
                'weapon_type': 'bow',
                'equipment_slot': 'weapon'
            }
        ]

        for weapon_data in weapons_data:
            Weapon.objects.create(**weapon_data)
            self.stdout.write(f'✅ Created weapon: {weapon_data["name"]}')

        # Create armor
        armor_data = [
            {
                'name': 'Leather Vest',
                'description': 'Basic leather protection for adventurers',
                'value': 50,
                'defense': 15,
                'armor_type': 'leather',
                'equipment_slot': 'chest'
            },
            {
                'name': 'Iron Helmet',
                'description': 'Sturdy iron protection for your head',
                'value': 75,
                'defense': 10,
                'armor_type': 'iron',
                'equipment_slot': 'head'
            },
            {
                'name': 'Chainmail Armor',
                'description': 'Flexible metal links provide good protection',
                'value': 250,
                'defense': 30,
                'armor_type': 'chainmail',
                'equipment_slot': 'chest'
            },
            {
                'name': 'Plate Boots',
                'description': 'Heavy metal boots for maximum protection',
                'value': 150,
                'defense': 12,
                'armor_type': 'plate',
                'equipment_slot': 'feet'
            }
        ]

        for armor_item in armor_data:
            Armor.objects.create(**armor_item)
            self.stdout.write(f'🛡️ Created armor: {armor_item["name"]}')

        # Create off-hand items
        offhand_data = [
            {
                'name': 'Wooden Shield',
                'description': 'A basic wooden shield for defense',
                'value': 40,
                'block': 5,
                'shield_type': 'wooden',
                'equipment_slot': 'shield'
            },
            {
                'name': 'Iron Shield',
                'description': 'A sturdy iron shield that blocks attacks',
                'value': 120,
                'block': 15,
                'shield_type': 'iron',
                'equipment_slot': 'shield'
            }
        ]

        for offhand_item in offhand_data:
            OffHand.objects.create(**offhand_item)
            self.stdout.write(f'🛡️ Created off-hand: {offhand_item["name"]}')

        # Create consumables
        consumables_data = [
            {
                'name': 'Health Potion',
                'description': 'Restores health when consumed',
                'value': 25,
                'heal_amount': 50,
                'mana_restore': 0,
                'duration': 0
            },
            {
                'name': 'Mana Potion',
                'description': 'Restores magical energy',
                'value': 30,
                'heal_amount': 0,
                'mana_restore': 75,
                'duration': 0
            },
            {
                'name': 'Super Healing Potion',
                'description': 'Powerful healing elixir',
                'value': 100,
                'heal_amount': 200,
                'mana_restore': 50,
                'duration': 0
            },
            {
                'name': 'Strength Buff',
                'description': 'Temporarily increases your strength',
                'value': 60,
                'heal_amount': 0,
                'mana_restore': 0,
                'duration': 300  # 5 minutes
            }
        ]

        for consumable_data in consumables_data:
            Consumable.objects.create(**consumable_data)
            self.stdout.write(f'🧪 Created consumable: {consumable_data["name"]}')

        # Summary
        total_items = Item.objects.count()
        total_value = sum(item.value for item in Item.objects.all())

        self.stdout.write(
            self.style.SUCCESS(
                f'\n🎉 Successfully created {total_items} items worth {total_value} gold total!'
            )
        )

        self.stdout.write('\n📊 Item breakdown:')
        self.stdout.write(f'  🗡️ Weapons: {Weapon.objects.count()}')
        self.stdout.write(f'  🛡️ Armor: {Armor.objects.count()}')
        self.stdout.write(f'  🛡️ Off-hand: {OffHand.objects.count()}')
        self.stdout.write(f'  🧪 Consumables: {Consumable.objects.count()}')

        self.stdout.write(f'\n🌐 Visit http://127.0.0.1:8000/inventory/ to see your items!')
