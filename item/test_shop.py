from datetime import timedelta
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from django.db import close_old_connections, OperationalError
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from hero.models import Hero, HeroClass
from item.models import (Weapon, Armor, Accessory, Consumable, Instant, Item,
                         InventoryItem, Equipment, EquipmentSlot, ShopState)
from item.services import receive_item
from item import shop


class ShopTests(TestCase):
    def setUp(self):
        self.cls = HeroClass.objects.create(name='Shop Warrior')
        self.hero = Hero.objects.create(name='Shop Hero', hero_class=self.cls, level=3, money=100)
        self.weapon = Weapon.objects.create(name='Sword', value=21, level_requirement=3, hero_class_restriction=self.cls)
        self.potion = Consumable.objects.create(name='Potion', value=6)
        self.armor = Armor.objects.create(name='Armor', value=18)
        self.accessory = Accessory.objects.create(name='Ring', value=15)
        session = self.client.session
        session['hero_id'] = self.hero.pk
        session.save()

    def offer(self, item):
        return shop.stock_for(self.hero).offers.get(item=item)

    def test_selection_and_exclusions(self):
        other = HeroClass.objects.create(name='Other')
        for model, kwargs in [(Instant, {}), (Consumable, {'money_amount': 100}),
                              (Item, {}), (Weapon, {'value': 0}),
                              (Weapon, {'level_requirement': 4}),
                              (Weapon, {'hero_class_restriction': other})]:
            model.objects.create(name=f'Excluded {Item.objects.count()}', **({'value': 10} | kwargs))
        state = shop.stock_for(self.hero)
        self.assertEqual(set(state.offers.values_list('item_id', flat=True)),
                         {self.weapon.pk, self.potion.pk, self.armor.pk, self.accessory.pk})
        self.assertEqual(state.offers.get(item=self.potion).remaining, 5)
        for i in range(12):
            Weapon.objects.create(name=f'Extra {i}', value=10)
        state.expires_at = timezone.now()
        state.save()
        state = shop.stock_for(self.hero)
        self.assertEqual(state.offers.count(), 8)
        self.assertTrue(state.offers.filter(item=self.potion).exists())
        self.assertTrue(state.offers.filter(item=self.armor).exists())
        self.assertTrue(state.offers.filter(item=self.accessory).exists())

    def test_persistence_refresh_and_isolation(self):
        offer = self.offer(self.weapon)
        shop.buy(self.hero, offer.pk, 1)
        self.assertEqual(shop.stock_for(self.hero).offers.get(pk=offer.pk).remaining, 0)
        state = offer.shop
        state.expires_at = timezone.now() - timedelta(seconds=1)
        state.save()
        with self.assertRaisesMessage(ValueError, 'expired'):
            shop.buy(self.hero, offer.pk, 1)
        self.assertFalse(shop.stock_for(self.hero).offers.filter(pk=offer.pk).exists())
        other = Hero.objects.create(name='Other Hero', hero_class=self.cls, money=100)
        with self.assertRaises(ValueError):
            shop.buy(other, self.offer(self.weapon).pk, 1)
        self.hero.level = 6
        self.hero.save(update_fields=['level'])
        self.assertEqual(shop.stock_for(self.hero).offers.count(), 0)
        self.hero.level = 3
        self.hero.hero_class = HeroClass.objects.create(name='Wizard')
        self.hero.save(update_fields=['level', 'hero_class'])
        self.assertFalse(shop.stock_for(self.hero).offers.filter(item=self.weapon).exists())

    def test_buy_quantities_prices_and_rollback(self):
        offer = self.offer(self.potion)
        shop.buy(self.hero, offer.pk, 3)
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.money, 82)
        self.assertEqual(InventoryItem.objects.get(inventory=self.hero.inventory, item=self.potion).quantity, 3)
        for quantity in (0, -1, '1.5', True, 'no', 3):
            with self.assertRaises(ValueError):
                shop.buy(self.hero, offer.pk, quantity)
        with patch('item.shop.receive_item', side_effect=RuntimeError('failed')):
            with self.assertRaises(RuntimeError):
                shop.buy(self.hero, offer.pk, 1)
        self.hero.refresh_from_db()
        offer.refresh_from_db()
        self.assertEqual(self.hero.money, 82)
        self.assertEqual(offer.remaining, 2)
        self.hero.money = 0
        self.hero.save(update_fields=['money'])
        with self.assertRaisesMessage(ValueError, 'money'):
            shop.buy(self.hero, offer.pk, 1)

    def test_sell_spares_rounding_and_equipment(self):
        equipment = Equipment.objects.create(hero=self.hero)
        EquipmentSlot.objects.create(equipment=equipment, slot='weapon', item=self.weapon)
        with self.assertRaises(ValueError):
            shop.sell(self.hero, self.weapon.pk, 1)
        receive_item(self.hero, self.weapon, 2)
        shop.sell(self.hero, self.weapon.pk, 2)
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.money, 120)
        self.assertFalse(InventoryItem.objects.filter(inventory=self.hero.inventory, item=self.weapon).exists())
        self.assertEqual(equipment.slots.get().item_id, self.weapon.pk)
        worthless = Item.objects.create(name='Worthless', value=1)
        receive_item(self.hero, worthless)
        with self.assertRaisesMessage(ValueError, 'no sale value'):
            shop.sell(self.hero, worthless.pk, 1)

    def test_combat_and_changed_catalog(self):
        offer = self.offer(self.weapon)
        receive_item(self.hero, self.weapon)
        self.hero.is_in_combat = True
        self.hero.save(update_fields=['is_in_combat'])
        for operation, target in ((shop.buy, offer.pk), (shop.sell, self.weapon.pk)):
            with self.assertRaisesMessage(ValueError, 'combat'):
                operation(self.hero, target, 1)
        self.assertContains(self.client.get(reverse('shop')), 'Shopping is unavailable during combat.')
        self.hero.is_in_combat = False
        self.hero.save(update_fields=['is_in_combat'])
        self.weapon.level_requirement = 4
        self.weapon.save()
        with self.assertRaises(ValueError):
            shop.buy(self.hero, offer.pk, 1)

    def test_http_navigation_csrf_and_tampering(self):
        response = self.client.get(reverse('shop'))
        self.assertContains(response, 'Balance:')
        self.assertContains(response, reverse('inventory'))
        offer = self.offer(self.weapon)
        url = reverse('shop_buy', args=[offer.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.cookies = self.client.cookies
        self.assertEqual(strict.post(url, {'quantity': 1}).status_code, 403)
        strict.get(reverse('shop'))
        self.assertEqual(strict.post(url, {'quantity': 0,
            'csrfmiddlewaretoken': strict.cookies['csrftoken'].value}).status_code, 302)
        self.client.post(url, {'quantity': 1, 'price': 0, 'hero_id': 999}, follow=True)
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.money, 79)
        self.assertContains(self.client.get(reverse('shop')), 'Sold out.')
        self.assertEqual(Client().get(reverse('shop')).status_code, 302)
        self.assertEqual(Client().post(url).status_code, 302)
        from hero.components.home_screen import HomeScreenView
        self.assertEqual(HomeScreenView(component_name='home-screen', component_id='shop-test').navigate_to_shop().url, reverse('shop'))

    def test_empty_catalog_and_price_snapshot(self):
        offer = self.offer(self.weapon)
        self.weapon.value = 90
        self.weapon.save()
        shop.buy(self.hero, offer.pk, 1)
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.money, 79)
        for item in Item.objects.all():
            item.delete()
        self.assertContains(self.client.get(reverse('shop')), 'No items are available')


class ShopConcurrencyTests(TransactionTestCase):
    def test_competing_buyers_cannot_duplicate_stock(self):
        cls = HeroClass.objects.create(name='Concurrent')
        hero = Hero.objects.create(name='Concurrent', hero_class=cls, money=10)
        item = Weapon.objects.create(name='Last sword', value=10)
        offer = shop.stock_for(hero).offers.get()

        def purchase(_):
            close_old_connections()
            try:
                shop.buy(Hero.objects.get(pk=hero.pk), offer.pk, 1)
                return True
            except (ValueError, OperationalError):
                return False
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(purchase, range(2)))
        self.assertEqual(sum(results), 1)
        hero.refresh_from_db()
        offer.refresh_from_db()
        self.assertEqual(hero.money, 0)
        self.assertEqual(offer.remaining, 0)
        self.assertEqual(InventoryItem.objects.get(inventory=hero.inventory, item=item).quantity, 1)

    def test_competing_offers_cannot_overspend(self):
        cls = HeroClass.objects.create(name='Budget')
        hero = Hero.objects.create(name='Budget', hero_class=cls, money=10)
        Weapon.objects.create(name='Budget sword', value=10)
        Armor.objects.create(name='Budget armor', value=10)
        offers = list(shop.stock_for(hero).offers.values_list('pk', flat=True))

        def purchase(offer_id):
            close_old_connections()
            try:
                shop.buy(Hero.objects.get(pk=hero.pk), offer_id, 1)
                return True
            except (ValueError, OperationalError):
                return False
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(sum(executor.map(purchase, offers)), 1)
        hero.refresh_from_db()
        self.assertEqual(hero.money, 0)
        self.assertEqual(InventoryItem.objects.get(inventory=hero.inventory).quantity, 1)

    def test_competing_sales_cannot_duplicate_money(self):
        cls = HeroClass.objects.create(name='Seller')
        hero = Hero.objects.create(name='Seller', hero_class=cls, money=0)
        item = Weapon.objects.create(name='Sale sword', value=10)
        receive_item(hero, item)

        def sale(_):
            close_old_connections()
            try:
                shop.sell(Hero.objects.get(pk=hero.pk), item.pk, 1)
                return True
            except (ValueError, OperationalError):
                return False
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(sum(executor.map(sale, range(2))), 1)
        hero.refresh_from_db()
        self.assertEqual(hero.money, 5)
        self.assertFalse(InventoryItem.objects.filter(inventory=hero.inventory).exists())
