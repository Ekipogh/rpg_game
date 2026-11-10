"""Immediate item receipt and consumable regressions."""
from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from hero.models import Hero, HeroClass
from .models import Instant, Consumable, Item, Inventory, InventoryItem
from .services import receive_item


class InstantItemTests(TestCase):
    def setUp(self):
        self.hero = Hero.objects.create(name='Receiver', hero_class=HeroClass.objects.create(name='Warrior'),
            current_health=50, current_mana=20, money=7)
        self.purse = Instant.objects.create(name='Coin purse', money_amount=25)

    def test_money_receipt_uses_whole_stack_without_inventory(self):
        self.hero.add_to_inventory(self.purse, 3)
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.money, 82)
        self.assertEqual(self.hero.current_health, 50)
        self.assertIsNone(self.hero.inventory_id)
        self.assertFalse(Inventory.objects.exists())
        self.assertFalse(InventoryItem.objects.exists())

    def test_base_item_and_consumable_references_resolve_instant_subclass(self):
        base = Item.objects.non_polymorphic().get(pk=self.purse.pk)
        parent = Consumable.objects.non_polymorphic().get(pk=self.purse.pk)
        self.hero.add_to_inventory(base, 2)
        self.hero.add_to_inventory(parent, 2)
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.money, 107)
        self.assertIsNone(self.hero.inventory_id)

    def test_stale_hero_cannot_overwrite_resources_or_money(self):
        Hero.objects.filter(pk=self.hero.pk).update(money=100, current_health=80, current_mana=40)
        self.hero.add_to_inventory(self.purse, 2)
        self.hero.refresh_from_db()
        self.assertEqual((self.hero.money, self.hero.current_health, self.hero.current_mana), (150, 80, 40))

    def test_healing_and_mana_stack_and_caps(self):
        item = Instant.objects.create(name='Restoration', heal_amount=30, mana_restore=20)
        self.hero.add_to_inventory(item, 3)
        self.hero.refresh_from_db()
        self.assertEqual((self.hero.current_health, self.hero.current_mana), (100, 50))
        self.assertFalse(InventoryItem.objects.exists())

    def test_instant_use_does_not_remove_inventory(self):
        inventory = Inventory.objects.create()
        Hero.objects.filter(pk=self.hero.pk).update(inventory=inventory)
        ordinary = Consumable.objects.create(name='Potion')
        stock = InventoryItem.objects.create(inventory=inventory, item=ordinary, quantity=3)
        with patch.object(Hero, 'remove_item', side_effect=AssertionError('Instant must not consume stock')):
            self.purse.use(self.hero, quantity=2)
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 3)
        self.assertEqual(self.hero.money, 57)

    def test_ordinary_items_remain_in_inventory(self):
        item = Consumable.objects.create(name='Potion')
        self.hero.add_to_inventory(item, 3)
        self.hero.add_to_inventory(item, 2)
        self.assertEqual(InventoryItem.objects.get(item=item).quantity, 5)
        self.assertEqual(self.hero.money, 7)

    def test_invalid_quantity_has_no_effect(self):
        for quantity in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                self.hero.add_to_inventory(self.purse, quantity)
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.money, 7)
        self.assertFalse(Inventory.objects.exists())

    def test_manual_api_cannot_mint_money(self):
        session = self.client.session; session['hero_id'] = self.hero.pk; session.save()
        url = reverse('use_item_api', args=[self.purse.pk])
        for _ in range(2):
            self.assertEqual(self.client.post(url).status_code, 400)
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.money, 7)
        response = self.client.get(reverse('item_detail', args=[self.purse.pk]))
        self.assertContains(response, 'Used automatically when received.')
        self.assertContains(response, 'Adds <span class="currency" aria-label="2 silver 5 copper"><span class="currency-denomination"><img class="currency-coin" src="/media/coin/Coin_Silver_0.png" alt="" width="24" height="24">2 silver')
        self.assertNotContains(response, '>🧪 Use Item</button>')

    def test_normal_money_consumable_requires_stock_and_consumes_once(self):
        item = Consumable.objects.create(name='Stored purse', heal_amount=0, money_amount=10)
        session = self.client.session; session['hero_id'] = self.hero.pk; session.save()
        url = reverse('use_item_api', args=[item.pk])
        self.assertEqual(self.client.post(url).status_code, 400)
        self.hero.add_to_inventory(item, 2)
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertEqual(InventoryItem.objects.get(item=item).quantity, 1)
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertEqual(self.client.post(url).status_code, 400)
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.money, 27)
