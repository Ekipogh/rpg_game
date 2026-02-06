# Generated manually to update stats to match BATTLE_SYSTEM.md

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hero', '0011_alter_hero_inventory'),
    ]

    operations = [
        # Remove old Hero fields (they will be replaced with new stat system)
        migrations.RemoveField(
            model_name='hero',
            name='strength',
        ),
        migrations.RemoveField(
            model_name='hero',
            name='agility',
        ),
        migrations.RemoveField(
            model_name='hero',
            name='intelligence',
        ),
        migrations.RemoveField(
            model_name='hero',
            name='constitution',
        ),

        # Remove old HeroClass fields
        migrations.RemoveField(
            model_name='heroclass',
            name='base_strength',
        ),
        migrations.RemoveField(
            model_name='heroclass',
            name='base_constitution',
        ),
        migrations.RemoveField(
            model_name='heroclass',
            name='base_agility',
        ),
        migrations.RemoveField(
            model_name='heroclass',
            name='base_intelligence',
        ),

        # Add new HeroClass base stats
        migrations.AddField(
            model_name='heroclass',
            name='base_mana',
            field=models.IntegerField(default=50),
        ),
        migrations.AddField(
            model_name='heroclass',
            name='base_attack',
            field=models.IntegerField(default=10),
        ),
        migrations.AddField(
            model_name='heroclass',
            name='base_defense',
            field=models.IntegerField(default=10),
        ),
        migrations.AddField(
            model_name='heroclass',
            name='base_magic',
            field=models.IntegerField(default=10),
        ),
        migrations.AddField(
            model_name='heroclass',
            name='base_magic_defense',
            field=models.IntegerField(default=10),
        ),
        migrations.AddField(
            model_name='heroclass',
            name='base_speed',
            field=models.IntegerField(default=10),
        ),

        # Add HeroClass stat growth ranges
        migrations.AddField(
            model_name='heroclass',
            name='atk_gain_min',
            field=models.IntegerField(default=1),
        ),
        migrations.AddField(
            model_name='heroclass',
            name='atk_gain_max',
            field=models.IntegerField(default=2),
        ),
        migrations.AddField(
            model_name='heroclass',
            name='def_gain_min',
            field=models.IntegerField(default=1),
        ),
        migrations.AddField(
            model_name='heroclass',
            name='def_gain_max',
            field=models.IntegerField(default=2),
        ),
        migrations.AddField(
            model_name='heroclass',
            name='mag_gain_min',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='heroclass',
            name='mag_gain_max',
            field=models.IntegerField(default=1),
        ),
        migrations.AddField(
            model_name='heroclass',
            name='mdef_gain_min',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='heroclass',
            name='mdef_gain_max',
            field=models.IntegerField(default=1),
        ),
        migrations.AddField(
            model_name='heroclass',
            name='spd_gain_min',
            field=models.IntegerField(default=1),
        ),
        migrations.AddField(
            model_name='heroclass',
            name='spd_gain_max',
            field=models.IntegerField(default=2),
        ),
        migrations.AddField(
            model_name='heroclass',
            name='hp_gain_min',
            field=models.IntegerField(default=5),
        ),
        migrations.AddField(
            model_name='heroclass',
            name='hp_gain_max',
            field=models.IntegerField(default=10),
        ),
        migrations.AddField(
            model_name='heroclass',
            name='mp_gain_min',
            field=models.IntegerField(default=2),
        ),
        migrations.AddField(
            model_name='heroclass',
            name='mp_gain_max',
            field=models.IntegerField(default=5),
        ),

        # Add new Hero primary stats (BATTLE_SYSTEM.md)
        # These replace the old strength, agility, intelligence, constitution fields
        migrations.AddField(
            model_name='hero',
            name='attack',
            field=models.IntegerField(default=10),
        ),
        migrations.AddField(
            model_name='hero',
            name='defense',
            field=models.IntegerField(default=10),
        ),
        migrations.AddField(
            model_name='hero',
            name='magic',
            field=models.IntegerField(default=10),
        ),
        migrations.AddField(
            model_name='hero',
            name='magic_defense',
            field=models.IntegerField(default=10),
        ),
        migrations.AddField(
            model_name='hero',
            name='speed',
            field=models.IntegerField(default=10),
        ),

        # Add new Hero secondary stats (BATTLE_SYSTEM.md)
        migrations.AddField(
            model_name='hero',
            name='accuracy',
            field=models.IntegerField(default=100),
        ),
        migrations.AddField(
            model_name='hero',
            name='evasion',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='hero',
            name='critical_chance',
            field=models.IntegerField(default=5),
        ),
        migrations.AddField(
            model_name='hero',
            name='critical_damage',
            field=models.FloatField(default=1.5),
        ),
    ]
