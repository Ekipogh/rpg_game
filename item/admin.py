from django.contrib import admin

from item.models import Consumable, Item, Weapon, OfHand, Armor

# Register your models here.
admin.site.register(Weapon)
admin.site.register(OfHand)
admin.site.register(Armor)
admin.site.register(Consumable)