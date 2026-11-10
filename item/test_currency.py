from django.test import SimpleTestCase, TestCase, override_settings
from django.contrib.staticfiles import finders
from django.core.management import call_command
from tempfile import TemporaryDirectory
from pathlib import Path
from django.urls import reverse

from game.currency import format_currency, render_currency
from hero.models import Hero, HeroClass
from item.models import Inventory, InventoryItem, Item
from item.views import serialize_inventory_item


class CurrencyTests(SimpleTestCase):
    def test_denominations(self):
        for amount, expected in (
            (0, "0 copper"), (6, "6 copper"), (10, "1 silver"),
            (99, "9 silver 9 copper"), (100, "1 gold"),
            (126, "1 gold 2 silver 6 copper"), (1000, "10 gold"),
            (-126, "-1 gold 2 silver 6 copper"),
        ):
            with self.subTest(amount=amount):
                self.assertEqual(format_currency(amount), expected)


    @override_settings(STATIC_URL="/assets/", MEDIA_URL="/uploads/")
    def test_coin_artwork_is_collected_and_uses_static_urls(self):
        html = render_currency(126)
        with TemporaryDirectory() as directory:
            with override_settings(STATIC_ROOT=directory):
                call_command("collectstatic", interactive=False, verbosity=0)
            for coin in ("Gold", "Silver", "Cupper"):
                asset = f"coin/Coin_{coin}_0.png"
                self.assertIn(f'/assets/{asset}', html)
                self.assertEqual((Path(directory) / asset).read_bytes(),
                                 Path(finders.find(asset)).read_bytes())
        self.assertNotIn("/uploads/", html)


class CurrencyDisplayTests(TestCase):
    def test_balance_and_item_values(self):
        hero_class = HeroClass.objects.create(name="Warrior")
        inventory = Inventory.objects.create()
        hero = Hero.objects.create(name="Rich hero", hero_class=hero_class,
                                   money=126, inventory=inventory)
        item = Item.objects.create(name="Copper trinket", value=6)
        InventoryItem.objects.create(inventory=inventory, item=item, quantity=2)
        session = self.client.session
        session["hero_id"] = hero.pk
        session.save()
        for page in ("home", "inventory"):
            with self.subTest(page=page):
                response = self.client.get(reverse(page))
                self.assertContains(response, 'aria-label="1 gold 2 silver 6 copper"')
                for coin in ("Gold", "Silver", "Cupper"):
                    self.assertContains(response, f"/static/coin/Coin_{coin}_0.png")
        response = self.client.get(reverse("inventory"))
        self.assertContains(response, "6 copper")
        self.assertContains(self.client.get(f"/item/{item.pk}/"), "6 copper")
        self.assertEqual(serialize_inventory_item(item)["formatted_value"], "6 copper")

        home = self.client.get(reverse("home")).content.decode()
        self.assertLess(home.index("XP</small>"), home.index('aria-label="1 gold 2 silver 6 copper"'))
        self.assertIn("Coin_Cupper_0.png", serialize_inventory_item(item)["currency_html"])
