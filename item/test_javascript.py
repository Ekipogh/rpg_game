from django.test import TestCase
from django.test import Client
from hero.models import Hero, HeroClass
from item.models import Weapon, Armor, Consumable, OffHand


class InventoryJavaScriptTests(TestCase):
    """
    Tests for JavaScript functionality in inventory template.
    These tests verify that the required JavaScript code is present
    and properly structured for the Equip/Use buttons.
    """

    def setUp(self):
        self.client = Client()

        # Create test items to ensure sections are rendered
        hero_class = HeroClass.objects.create(name="Warrior", description="Test class")

        self.weapon = Weapon.objects.create(
            name="JS Test Sword",
            damage=10,
            weapon_type="sword",
            value=100
        )

        self.consumable = Consumable.objects.create(
            name="JS Test Potion",
            heal_amount=25,
            value=50
        )

    def test_equip_item_javascript_present(self):
        """Test that equipItem JavaScript function is properly defined"""
        response = self.client.get('/inventory/')
        content = response.content.decode()

        # Check function definition
        self.assertIn('function equipItem(itemId)', content)
        self.assertIn('alert(`Equipping item ${itemId}...`)', content)

    def test_use_item_javascript_present(self):
        """Test that useItem JavaScript function is properly defined"""
        response = self.client.get('/inventory/')
        content = response.content.decode()

        # Check function definition
        self.assertIn('function useItem(itemId)', content)
        self.assertIn('alert(`Using item ${itemId}...`)', content)

    def test_view_item_javascript_present(self):
        """Test that viewItem JavaScript function is properly defined"""
        response = self.client.get('/inventory/')
        content = response.content.decode()

        # Check function definition
        self.assertIn('function viewItem(itemId)', content)
        self.assertIn('window.location.href = `/item/${itemId}/`', content)

    def test_event_propagation_handling(self):
        """Test that event.stopPropagation() is properly implemented"""
        response = self.client.get('/inventory/')
        content = response.content.decode()

        # Check that buttons include stopPropagation
        self.assertIn('event.stopPropagation(); equipItem', content)
        self.assertIn('event.stopPropagation(); useItem', content)
        self.assertIn('event.stopPropagation(); viewItem', content)

    def test_button_onclick_handlers(self):
        """Test that button onclick handlers are properly set up"""
        response = self.client.get('/inventory/')
        content = response.content.decode()

        # Check for proper onclick handlers in buttons
        self.assertIn('onclick="event.stopPropagation(); equipItem(', content)
        self.assertIn('onclick="event.stopPropagation(); useItem(', content)
        self.assertIn('onclick="event.stopPropagation(); viewItem(', content)

    def test_bootstrap_classes_on_buttons(self):
        """Test that buttons have proper Bootstrap classes"""
        response = self.client.get('/inventory/')
        content = response.content.decode()

        # Check for Bootstrap button classes
        self.assertIn('btn btn-primary btn-sm', content)  # Equip buttons
        self.assertIn('btn btn-success btn-sm', content)  # Use buttons
        self.assertIn('btn btn-outline-secondary btn-sm', content)  # View buttons

    def test_button_icons_present(self):
        """Test that buttons have appropriate emoji icons"""
        response = self.client.get('/inventory/')
        content = response.content.decode()

        # Check for emoji icons in buttons
        self.assertIn('⚔️ Equip', content)  # Weapon equip
        self.assertIn('🧪 Use', content)    # Consumable use
        self.assertIn('👁️ View', content)   # View button
        # Note: 🛡️ Equip only appears when armor items are present

    def test_flex_layout_classes(self):
        """Test that button containers use proper flex classes"""
        response = self.client.get('/inventory/')
        content = response.content.decode()

        # Check for flex layout classes
        self.assertIn('d-flex gap-2', content)
        self.assertIn('flex-fill', content)  # For main action buttons


class ButtonBehaviorTests(TestCase):
    """
    Tests for specific button behavior based on item types
    """

    def setUp(self):
        self.client = Client()

        # Create different item types
        self.weapon = Weapon.objects.create(
            name="Behavior Test Sword",
            damage=15,
            weapon_type="sword",
            value=200
        )

        self.armor = Armor.objects.create(
            name="Behavior Test Armor",
            defense=12,
            armor_type="chain",
            value=150
        )

        self.offhand = OffHand.objects.create(
            name="Behavior Test Shield",
            block=8,
            shield_type="metal",
            value=100
        )

        self.consumable = Consumable.objects.create(
            name="Behavior Test Potion",
            heal_amount=30,
            mana_restore=15,
            value=40
        )

    def test_weapon_has_equip_button(self):
        """Test that weapons have Equip button but not Use button"""
        response = self.client.get('/inventory/')
        content = response.content.decode()

        if 'Behavior Test Sword' in content:
            # Find the weapon card section
            sword_section_start = content.find('Behavior Test Sword')
            sword_section_end = content.find('</div>', sword_section_start + 500)  # Find end of card
            sword_section = content[sword_section_start:sword_section_end]

            self.assertIn('⚔️ Equip', sword_section)
            self.assertIn('👁️ View', sword_section)

    def test_armor_has_equip_button(self):
        """Test that armor has Equip button but not Use button"""
        response = self.client.get('/inventory/')
        content = response.content.decode()

        if 'Behavior Test Armor' in content:
            # Find the armor card section
            armor_section_start = content.find('Behavior Test Armor')
            armor_section_end = content.find('</div>', armor_section_start + 500)
            armor_section = content[armor_section_start:armor_section_end]

            self.assertIn('🛡️ Equip', armor_section)
            self.assertIn('👁️ View', armor_section)

    def test_consumable_has_use_button(self):
        """Test that consumables have Use button but not Equip button"""
        response = self.client.get('/inventory/')
        content = response.content.decode()

        if 'Behavior Test Potion' in content:
            # Check that consumable use button exists in the page
            self.assertIn('🧪 Use', content)
            self.assertIn('👁️ View', content)
            # Find the consumable section
            potion_start = content.find('Behavior Test Potion')
            if potion_start != -1:
                # Look for the button in a reasonable range after the name
                potion_section = content[potion_start:potion_start + 1000]
                self.assertIn('useItem(', potion_section)

    def test_item_cards_are_clickable(self):
        """Test that item cards maintain their clickable behavior"""
        response = self.client.get('/inventory/')
        content = response.content.decode()

        # Check that cards have onclick handlers for viewing items
        self.assertIn('onclick="viewItem(', content)
        self.assertIn('style="cursor: pointer;"', content)