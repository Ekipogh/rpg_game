from django.db import migrations


def convert_experience(apps, schema_editor):
    Hero = apps.get_model("hero", "Hero")
    heroes = Hero.objects.using(schema_editor.connection.alias)
    for hero in heroes.filter(level__gt=0).iterator():
        # Retain overflow for legacy heroes whose leveling was previously delayed.
        progress = max(0, hero.experience - 100 * (hero.level - 1))
        experience = 50 * hero.level * (hero.level - 1) + progress * hero.level
        heroes.filter(pk=hero.pk).update(experience=experience)


def reverse_experience(apps, schema_editor):
    Hero = apps.get_model("hero", "Hero")
    heroes = Hero.objects.using(schema_editor.connection.alias)
    for hero in heroes.filter(level__gt=0).iterator():
        progress = max(0, hero.experience - 50 * hero.level * (hero.level - 1))
        experience = 100 * (hero.level - 1) + progress // hero.level
        heroes.filter(pk=hero.pk).update(experience=experience)


class Migration(migrations.Migration):
    dependencies = [("hero", "0027_hero_movement_policy")]
    operations = [migrations.RunPython(convert_experience, reverse_experience)]
