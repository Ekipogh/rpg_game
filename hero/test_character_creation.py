import json
from time import time

from bs4 import BeautifulSoup
from django_unicorn.utils import generate_checksum

from io import BytesIO
from tempfile import TemporaryDirectory

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from hero.components.character_form import CharacterFormView
from hero.models import HeroClass
from hero.models import Hero, HeroClassEquipment
from hero.creation import create_character
from item.models import Weapon, Inventory, Equipment
from unittest.mock import patch


class CharacterCreationTests(TestCase):
    def test_submit_uses_imported_equipment_and_database_stats(self):
        hero_class = HeroClass.objects.create(name='Custom class', base_attack=23)
        weapon = Weapon.objects.create(name='Configured sword', attack_bonus=5)
        HeroClassEquipment.objects.create(hero_class=hero_class, slot='weapon', item=weapon)
        component = CharacterFormView(component_name='character-form', component_id='test-character')
        component.select_class(hero_class.pk)
        component.name = 'New hero'
        component.attack_total = 999
        with patch.object(component, 'is_valid', return_value=True):
            response = component.submit()
        hero = Hero.objects.get(name='New hero')
        self.assertEqual(hero.attack, 23)
        self.assertEqual(hero.weapon, weapon)
        self.assertEqual(Weapon.objects.count(), 1)
        self.assertEqual(response.url, reverse('select_hero', kwargs={'hero_id': hero.pk}))

    def test_creation_rolls_back_when_loadout_is_invalid(self):
        hero_class = HeroClass.objects.create(name='Custom class')
        weapon = Weapon.objects.create(name='Wrong slot')
        HeroClassEquipment.objects.create(hero_class=hero_class, slot='armor', item=weapon)
        with self.assertRaises(ValidationError):
            create_character('Invalid hero', hero_class)
        self.assertEqual(Hero.objects.count(), 0)
        self.assertEqual(Inventory.objects.count(), 0)
        self.assertEqual(Equipment.objects.count(), 0)

    def test_screen_uses_current_database_classes(self):
        hero_class = HeroClass.objects.create(
            name="Alchemist's Apprentice", description="Brews potions.", base_attack=23,
        )
        response = self.client.get(reverse("create_character"))
        self.assertContains(response, "Alchemist's Apprentice")
        self.assertContains(response, "Brews potions.")
        self.assertContains(response, f'select_class({hero_class.pk})')
        self.assertNotContains(response, "select_class('Warrior')")
        self.assertNotContains(response, "images/alchemist")

    def test_mount_and_selection_use_class_ids_and_current_stats(self):
        first = HeroClass.objects.create(name="Same name", base_attack=23)
        second = HeroClass.objects.create(name="Same name", base_attack=37)
        component = CharacterFormView(component_name="character-form", component_id="test-character")
        component.mount()
        self.assertEqual(component.selected_class, first.pk)
        self.assertEqual(component.attack_total, 23)
        component.attack_mod = 2
        component.select_class(second.pk)
        self.assertEqual(component.selected_class, second.pk)
        self.assertEqual(component.attack_total, 39)
        component.select_class(second.pk + 1)
        self.assertEqual(component.selected_class, second.pk)
        second.delete()
        component.name = "New hero"
        with self.assertRaises(ValidationError) as error:
            component.validate_form()
        self.assertIn("selected_class", error.exception.message_dict)

    def test_empty_class_list(self):
        response = self.client.get(reverse("create_character"))
        self.assertContains(response, "No classes are available.")
        self.assertContains(response, 'unicorn:click="submit" disabled')

    def test_uploaded_class_image_survives_rename(self):
        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            image_data = BytesIO()
            Image.new("RGB", (2, 2)).save(image_data, format="PNG")
            hero_class = HeroClass.objects.create(
                name="Warrior",
                image=SimpleUploadedFile("portrait.png", image_data.getvalue(), content_type="image/png"),
            )
            hero_class.name = "Renamed class"
            hero_class.save()
            response = self.client.get(reverse("create_character"))
            self.assertContains(response, hero_class.image.url)
            self.assertContains(response, "Renamed class")
            self.assertTrue(hero_class.image.storage.exists(hero_class.image.name))

    def test_class_without_image_does_not_render_an_image(self):
        HeroClass.objects.create(name="Warrior")
        response = self.client.get(reverse("create_character"))
        self.assertNotContains(response, "<img")

    def test_class_selection_message_round_trip(self):
        first = HeroClass.objects.create(name="Warrior", base_attack=15)
        second = HeroClass.objects.create(
            name="Mage", base_attack=7, image="hero_classes/mage.png",
        )
        page = self.client.get(reverse("create_character"))
        soup = BeautifulSoup(page.content, "html.parser")
        root = soup.find(attrs={"unicorn:id": True})
        self.assertIsNotNone(root, "Character form component was not rendered")
        component_id = root["unicorn:id"]
        checksum_field = "meta" if root.has_attr("unicorn:meta") else "checksum"
        if root.has_attr("unicorn:data"):
            # Unicorn 0.67 embeds state directly on the component root.
            data = json.loads(root["unicorn:data"])
        else:
            # Older local environments embed it in a separate JSON script.
            script = soup.find("script", id=f"unicorn:data:{component_id}")
            self.assertIsNotNone(script, "Character form state was not rendered")
            data = json.loads(script.string)["data"]
        self.assertEqual(data["selected_class"], first.pk)
        for chosen in (second, first):
            response = self.client.post(
                "/unicorn/message/character-form",
                data={
                    "id": component_id,
                    "data": data,
                    checksum_field: generate_checksum(data),
                    "epoch": time(),
                    "actionQueue": [{
                        "type": "callMethod",
                        "payload": {"name": f"select_class({chosen.pk})"},
                    }],
                },
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertNotIn("error", result, result)
            data.update(result["data"])
            self.assertEqual(data["selected_class"], chosen.pk)
            self.assertEqual(data["attack_total"], chosen.base_attack)
            self.assertIn(second.image.url, result["dom"])
        self.assertNotIn("hero_classes", data)
