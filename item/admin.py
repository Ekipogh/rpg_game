from django.contrib import admin

from item.models import Consumable, Item, Weapon, OffHand, Armor, Accessory

# Register your models here.
admin.site.register(Weapon)
admin.site.register(OffHand)
admin.site.register(Armor)
admin.site.register(Accessory)
admin.site.register(Consumable)