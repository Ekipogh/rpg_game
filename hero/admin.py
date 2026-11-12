from django.contrib import admin
from django.urls import path

from hero.content_admin import import_content

from hero.models import Hero, HeroClass, Monster, MonsterLoot


class HeroAdmin(admin.ModelAdmin):
    list_display = ("name", "level", "hero_class", "level", "current_health", "max_health", "experience")
    search_fields = ("name",)
    list_filter = ("hero_class",)


class HeroClassAdmin(admin.ModelAdmin):
    change_list_template = "admin/hero/hero_class_change_list.html"

    def get_urls(self):
        return [path("import-content/", self.admin_site.admin_view(
            lambda request: import_content(request, self.admin_site)
        ), name="hero_content_import")] + super().get_urls()

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
        "threat_level",
        "current_health",
        "max_health",
        "attack",
        "defense",
        "magic",
        "magic_defense",
        "speed",
        "experience_reward",
    )
    search_fields = ("name",)
    list_filter = ("level", "threat_level")
    inlines = [MonsterLootInline]


# Register your models here.
admin.site.register(Hero, HeroAdmin)
admin.site.register(HeroClass, HeroClassAdmin)
admin.site.register(Monster, MonsterAdmin)
admin.site.register(MonsterLoot)
