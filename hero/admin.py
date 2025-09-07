from django.contrib import admin

from hero.models import Hero, HeroClass

# Register your models here.
admin.site.register(Hero)
admin.site.register(HeroClass)

class HeroAdmin(admin.ModelAdmin):
    list_display = ('name', 'level', 'hero_class', 'health')
    search_fields = ('name',)
    list_filter = ('hero_class',)

class HeroClassAdmin(admin.ModelAdmin):
    list_display = ('name', 'base_health', 'base_strength', 'base_agility', 'base_intelligence')
    search_fields = ('name',)
