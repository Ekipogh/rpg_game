from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.db import migrations, models


def preserve_class_artwork(apps, schema_editor):
    HeroClass = apps.get_model("hero", "HeroClass")
    for name in ("Warrior", "Ranger", "Wizard"):
        source = Path(settings.BASE_DIR) / "static" / "images" / f"{name.lower()}.png"
        if not source.is_file():
            continue
        for hero_class in HeroClass.objects.using(schema_editor.connection.alias).filter(name=name, image=""):
            with source.open("rb") as image_file:
                hero_class.image.save(source.name, File(image_file), save=False)
            hero_class.save(using=schema_editor.connection.alias, update_fields=["image"])


class Migration(migrations.Migration):
    dependencies = [("hero", "0021_rename_gold_hero_money")]

    operations = [
        migrations.AddField(
            model_name="heroclass",
            name="image",
            field=models.ImageField(blank=True, upload_to="hero_classes/"),
        ),
        migrations.RunPython(preserve_class_artwork, migrations.RunPython.noop),
    ]
