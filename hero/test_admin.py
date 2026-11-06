from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from decimal import Decimal
from tempfile import TemporaryDirectory
from threading import Event
from pathlib import Path
import sqlite3

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.backends.sqlite3.base import DatabaseWrapper
from django.forms.models import model_to_dict
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from hero.models import Monster, MonsterLoot
from item.models import Item


class MonsterLootAdminTests(TestCase):
    def test_add_loot_through_monster_change_page(self):
        self.client.force_login(get_user_model().objects.create_superuser(
            username="admin", password="test-password", email="admin@example.com"
        ))
        monster = Monster.objects.create(name="Loot monster")
        item = Item.objects.create(name="Loot item")
        data = model_to_dict(monster)
        data.update({
            "loot-TOTAL_FORMS": "1",
            "loot-INITIAL_FORMS": "0",
            "loot-MIN_NUM_FORMS": "0",
            "loot-MAX_NUM_FORMS": "1000",
            "loot-0-monster": str(monster.pk),
            "loot-0-item": str(item.pk),
            "loot-0-drop_chance": "25.50",
            "loot-0-min_quantity": "1",
            "loot-0-max_quantity": "3",
            "_save": "Save",
        })
        response = self.client.post(
            reverse("admin:hero_monster_change", args=[monster.pk]), data
        )
        self.assertEqual(response.status_code, 302)
        loot = MonsterLoot.objects.get(monster=monster)
        self.assertEqual(loot.item_id, item.pk)
        self.assertEqual(loot.drop_chance, Decimal("25.50"))
        self.assertEqual((loot.min_quantity, loot.max_quantity), (1, 3))


class SQLiteWriteContentionTests(SimpleTestCase):
    def test_transaction_waits_for_writer_before_reading_and_saving(self):
        # A file database is essential: shared in-memory SQLite uses different
        # locking behavior. Never acquire locks on the development database.
        with TemporaryDirectory() as directory:
            config = deepcopy(settings.DATABASES["default"])
            config["NAME"] = str(Path(directory) / "contention.sqlite3")
            with closing(sqlite3.connect(config["NAME"], isolation_level=None)) as setup:
                setup.execute("CREATE TABLE counter (value INTEGER)")
                setup.execute("INSERT INTO counter VALUES (0)")
            writer = sqlite3.connect(config["NAME"], isolation_level=None)
            started, read = Event(), Event()

            def save_after_read():
                db = DatabaseWrapper(config, alias="contention")
                try:
                    db.ensure_connection()
                    started.set()
                    # Exercise Django's transaction entry using project options.
                    db.set_autocommit(False, force_begin_transaction_with_broken_autocommit=True)
                    with db.cursor() as cursor:
                        cursor.execute("SELECT value FROM counter")
                        value = cursor.fetchone()[0]
                        read.set()
                        cursor.execute("UPDATE counter SET value = %s", [value + 1])
                    db.commit()
                    return value
                finally:
                    db.close()

            try:
                writer.execute("BEGIN IMMEDIATE")
                writer.execute("UPDATE counter SET value = 10")
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(save_after_read)
                    try:
                        self.assertTrue(started.wait(5))
                        self.assertFalse(read.wait(0.2))
                    finally:
                        writer.commit()
                    self.assertEqual(future.result(timeout=5), 10)
                self.assertEqual(writer.execute("SELECT value FROM counter").fetchone()[0], 11)
            finally:
                writer.close()
