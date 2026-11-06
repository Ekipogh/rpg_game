from django.contrib import admin

from item.models import Consumable, Weapon, Armor, Accessory, Instant

# Register your models here.
admin.site.register(Weapon)
admin.site.register(Armor)
admin.site.register(Accessory)
admin.site.register(Consumable)
admin.site.register(Instant)
