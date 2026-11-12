from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from hero.models import Monster


CATALOG = b"""schema_version: 1
items: []
monsters:
  - key: browser_monster
    name: Browser monster
monster_loot: []
encounters: []
"""


class ContentAdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("importer", "admin@example.com", "password")
        self.client.force_login(self.user)
        self.url = reverse("admin:hero_content_import")

    def post_catalog(self, action="validate", content=CATALOG):
        return self.client.post(self.url, {
            "action": action,
            "catalog": SimpleUploadedFile("rpg_content.yaml", content),
        })

    def test_discoverable_and_get_never_imports(self):
        response = self.client.get(reverse("admin:hero_heroclass_changelist"))
        self.assertContains(response, self.url)
        self.assertContains(self.client.get(self.url), "Validate only")
        self.assertFalse(Monster.objects.exists())

    def test_validate_then_apply_and_audit(self):
        self.assertContains(self.post_catalog(), "Dry run validated")
        self.assertFalse(Monster.objects.exists())
        self.assertFalse(LogEntry.objects.exists())
        self.assertContains(self.post_catalog("apply"), "Imported:")
        self.assertTrue(Monster.objects.filter(name="Browser monster").exists())
        entry = LogEntry.objects.get()
        self.assertEqual(entry.user_id, self.user.pk)
        self.assertIn("rpg_content.yaml", entry.change_message)

    def test_invalid_catalog_rolls_back_earlier_writes(self):
        invalid = CATALOG.replace(b"encounters: []", b"encounters:\n  - key: unknown\n    name: Invalid")
        self.assertContains(self.post_catalog("apply", invalid), "Content import failed")
        self.assertFalse(Monster.objects.exists())
        self.assertFalse(LogEntry.objects.exists())

    def test_bad_encoding_and_oversized_upload(self):
        self.assertContains(self.post_catalog("apply", b"\xff"), "codec")
        self.assertContains(self.post_catalog("apply", b" " * (2 * 1024 * 1024 + 1)), "at most 2 MiB")
        self.assertFalse(Monster.objects.exists())

    def test_requires_superuser_and_csrf(self):
        self.client.logout()
        self.assertEqual(self.post_catalog("apply").status_code, 302)
        staff = get_user_model().objects.create_user("staff", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.post_catalog("apply").status_code, 403)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(self.url, {"action": "apply"}).status_code, 403)
        self.assertFalse(Monster.objects.exists())
