from django.db import migrations, models


def forward(apps, schema_editor):
    Accessory = apps.get_model("item", "Accessory")
    for accessory in Accessory.objects.using(schema_editor.connection.alias).all().iterator():
        accessory.status_resistances = {
            "burning" if name == "burn" else name: 100
            for name in accessory.status_resistances
        }
        accessory.save(using=schema_editor.connection.alias, update_fields=["status_resistances"])


def backward(apps, schema_editor):
    Accessory = apps.get_model("item", "Accessory")
    for accessory in Accessory.objects.using(schema_editor.connection.alias).all().iterator():
        accessory.status_resistances = [
            name for name, value in accessory.status_resistances.items() if value == 100
        ]
        accessory.save(using=schema_editor.connection.alias, update_fields=["status_resistances"])


class Migration(migrations.Migration):
    dependencies = [("item", "0018_alter_accessory_options_alter_armor_options_and_more")]
    operations = [
        migrations.RenameField("accessory", "status_immunities", "status_resistances"),
        migrations.RunPython(forward, backward),
        migrations.AlterField("accessory", "status_resistances", models.JSONField(blank=True, default=dict)),
    ]
