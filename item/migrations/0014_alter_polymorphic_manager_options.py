from django.db import migrations


class Migration(migrations.Migration):
    """Record django-polymorphic's updated base-manager behavior (4.9+)."""

    dependencies = [
        ('item', '0013_instant_consumable_money_amount'),
    ]

    operations = [
        migrations.AlterModelOptions(name='accessory', options={}),
        migrations.AlterModelOptions(name='armor', options={}),
        migrations.AlterModelOptions(name='consumable', options={}),
        migrations.AlterModelOptions(name='instant', options={}),
        migrations.AlterModelOptions(name='item', options={}),
        migrations.AlterModelOptions(name='weapon', options={}),
    ]
