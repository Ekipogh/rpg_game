from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpRequest
from hero.models import Hero, HeroClass
from item.models import Item, Weapon, Armor, Consumable, OffHand, Inventory


class ItemViewTests(TestCase):
    def setUp(self):
        """Set up test data"""
        self.client = Client()

        # Create test hero class and hero
        self.hero_class = HeroClass.objects.create(
            name="Warrior",
            description="A brave warrior"
        )
        self.hero = Hero.objects.create(
            name="Test Hero",
            hero_class=self.hero_class,
            level=1,
            constitution=12,
            current_health=80,
            max_health=100,
            current_mana=60,
            max_mana=80
        )

        # Create test items
        self.weapon = Weapon.objects.create(
            name="Test Sword",
            description="A sharp sword",
            value=100,
            damage=15,
            weapon_type="sword"
        )

        self.armor = Armor.objects.create(
            name="Test Shield",
            description="A sturdy shield",
            value=80,
            defense=10,
            armor_type="plate"
        )

        self.consumable = Consumable.objects.create(
            name="Health Potion",
            description="Restores health",
            value=25,
            heal_amount=30,
            mana_restore=0,
            duration=0
        )

        self.other_item = Item.objects.create(
            name="Mysterious Key",
            description="An ancient key",
            value=50
        )

    def test_inventory_view_without_hero(self):
        """Test inventory view when no hero is selected"""
        response = self.client.get('/inventory/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inventory")

    def test_inventory_view_with_hero(self):
        """Test inventory view with hero in session"""
        # Add hero to session
        session = self.client.session
        session['hero_id'] = self.hero.id
        session.save()

        response = self.client.get('/inventory/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inventory")

    def test_item_detail_weapon(self):
        """Test item detail view for weapon"""
        response = self.client.get(f'/item/{self.weapon.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.weapon.name)
        self.assertContains(response, "Attack Damage")  # From the template
        self.assertContains(response, str(self.weapon.damage))

    def test_item_detail_armor(self):
        """Test item detail view for armor"""
        response = self.client.get(f'/item/{self.armor.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.armor.name)
        self.assertContains(response, "Defense Rating")  # From the template
        self.assertContains(response, str(self.armor.defense))

    def test_item_detail_consumable(self):
        """Test item detail view for consumable"""
        response = self.client.get(f'/item/{self.consumable.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.consumable.name)
        self.assertContains(response, "Health Restoration")  # From the template

    def test_item_detail_not_found(self):
        """Test item detail view for non-existent item"""
        response = self.client.get('/item/9999/')
        self.assertEqual(response.status_code, 404)

    def test_use_item_api_no_hero(self):
        """Test use item API without hero in session"""
        response = self.client.post(f'/item/{self.consumable.id}/use/')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertEqual(data['error'], 'No hero selected')

    def test_use_item_api_wrong_method(self):
        """Test use item API with GET instead of POST"""
        response = self.client.get(f'/item/{self.consumable.id}/use/')
        self.assertEqual(response.status_code, 405)
        data = response.json()
        self.assertIn('error', data)
        self.assertEqual(data['error'], 'POST required')

    def test_use_consumable_api(self):
        """Test using a consumable item via API"""
        # Add hero to session
        session = self.client.session
        session['hero_id'] = self.hero.id
        session.save()

        # Record initial health
        initial_health = self.hero.current_health

        response = self.client.post(f'/item/{self.consumable.id}/use/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['action_type'], 'consumed')
        self.assertEqual(data['item_type'], 'Consumable')

        # Verify hero health was updated
        self.hero.refresh_from_db()
        expected_health = min(initial_health + self.consumable.heal_amount, self.hero.max_health)
        self.assertEqual(self.hero.current_health, expected_health)

    def test_equip_weapon_api(self):
        """Test equipping a weapon via API"""
        # Add hero to session
        session = self.client.session
        session['hero_id'] = self.hero.id
        session.save()

        response = self.client.post(f'/item/{self.weapon.id}/use/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['action_type'], 'equipped')
        self.assertEqual(data['item_type'], 'Weapon')
        self.assertIn('Attack power increased', data['message'])

    def test_equip_armor_api(self):
        """Test equipping armor via API"""
        # Add hero to session
        session = self.client.session
        session['hero_id'] = self.hero.id
        session.save()

        response = self.client.post(f'/item/{self.armor.id}/use/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['action_type'], 'equipped')
        self.assertEqual(data['item_type'], 'Armor')
        self.assertIn('Defense increased', data['message'])

    def test_use_item_api_invalid_item(self):
        """Test use item API with non-existent item"""
        # Add hero to session
        session = self.client.session
        session['hero_id'] = self.hero.id
        session.save()

        response = self.client.post('/item/9999/use/')
        self.assertEqual(response.status_code, 404)


class InventoryTemplateTests(TestCase):
    def setUp(self):
        """Set up test data for template tests"""
        self.client = Client()

        # Create test items for template testing
        self.weapon = Weapon.objects.create(
            name="Template Sword",
            description="A sword for template testing",
            value=150,
            damage=20,
            weapon_type="sword"
        )

        self.armor = Armor.objects.create(
            name="Template Armor",
            description="Armor for template testing",
            value=120,
            defense=15,
            armor_type="leather"
        )

        self.consumable = Consumable.objects.create(
            name="Template Potion",
            description="A potion for template testing",
            value=30,
            heal_amount=40,
            mana_restore=20,
            duration=0
        )

    def test_inventory_template_contains_equip_buttons(self):
        """Test that inventory template contains Equip buttons for equipment"""
        response = self.client.get('/inventory/')
        self.assertEqual(response.status_code, 200)

        # Check for presence of equip buttons (they should be in the rendered HTML)
        self.assertContains(response, 'Equip')
        self.assertContains(response, 'equipItem')

    def test_inventory_template_contains_use_buttons(self):
        """Test that inventory template contains Use buttons for consumables"""
        response = self.client.get('/inventory/')
        self.assertEqual(response.status_code, 200)

        # Check for presence of use buttons
        self.assertContains(response, 'Use')
        self.assertContains(response, 'useItem')

    def test_inventory_template_contains_view_buttons(self):
        """Test that inventory template contains View buttons for all items"""
        response = self.client.get('/inventory/')
        self.assertEqual(response.status_code, 200)

        # Check for presence of view buttons
        self.assertContains(response, 'View')
        self.assertContains(response, 'viewItem')

    def test_inventory_template_javascript_functions(self):
        """Test that required JavaScript functions are present"""
        response = self.client.get('/inventory/')
        self.assertEqual(response.status_code, 200)

        # Check for JavaScript function definitions
        self.assertContains(response, 'function equipItem')
        self.assertContains(response, 'function useItem')
        self.assertContains(response, 'function viewItem')
        self.assertContains(response, 'event.stopPropagation()')

    def test_inventory_empty_state(self):
        """Test inventory template when no items are present"""
        # Use a fresh client session to avoid polymorphic cleanup issues
        empty_client = Client()

        response = empty_client.get('/inventory/')
        self.assertEqual(response.status_code, 200)

        # The view should handle empty inventory gracefully
        self.assertContains(response, "Inventory")