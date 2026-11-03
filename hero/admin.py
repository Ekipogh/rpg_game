from django.contrib import admin

from hero.models import Hero, HeroClass, Monster, MonsterLoot


class HeroAdmin(admin.ModelAdmin):
    list_display = ("name", "level", "hero_class", "level", "current_health", "max_health", "experience")
    search_fields = ("name",)
    list_filter = ("hero_class",)


class HeroClassAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "base_health",
        "base_attack",
        "base_defense",
        "base_magic",
        "base_magic_defense",
        "base_speed",
    )
    search_fields = ("name",)


class MonsterLootInline(admin.TabularInline):
    model = MonsterLoot
    extra = 1


class MonsterAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "level",
        "current_health",
        "max_health",
        "attack",
        "defense",
        "magic",
        "magic_defense",
        "speed",
    )
    search_fields = ("name",)
    list_filter = ("level",)
    inlines = [MonsterLootInline]


# Register your models here.
admin.site.register(Hero, HeroAdmin)
admin.site.register(HeroClass, HeroClassAdmin)
admin.site.register(Monster, MonsterAdmin)
admin.site.register(MonsterLoot)
