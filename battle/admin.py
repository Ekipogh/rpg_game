"""Battle inspection and encounter composition configuration."""
from django.contrib import admin
from django import forms
from hero.encounters import ENCOUNTER_DEFINITIONS
from .models import Battle, BattleCommand, BattleEvent, BattleWorkerLease, EncounterMonster


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Battle)
class BattleAdmin(ReadOnlyAdmin):
    list_display = ('id', 'hero', 'status', 'outcome', 'revision', 'created_at', 'resolved_at')
    list_filter = ('status', 'outcome')
    search_fields = ('hero__name', '=id')
    readonly_fields = tuple(field.name for field in Battle._meta.fields)


@admin.register(BattleEvent)
class BattleEventAdmin(ReadOnlyAdmin):
    list_display = ('battle', 'sequence', 'simulation_time_ms', 'event_type', 'actor_id', 'target_id')
    list_filter = ('event_type',)
    ordering = ('battle', 'sequence')


@admin.register(BattleCommand)
class BattleCommandAdmin(ReadOnlyAdmin):
    list_display = ('id', 'battle', 'sequence', 'command_type', 'status', 'reject_reason')
    list_filter = ('status', 'command_type')
    ordering = ('battle', 'sequence')


@admin.register(BattleWorkerLease)
class BattleWorkerLeaseAdmin(ReadOnlyAdmin):
    list_display = ('name', 'heartbeat_at', 'expires_at')


class CompositionForm(forms.ModelForm):
    encounter_definition_key = forms.ChoiceField(choices=[
        (key, definition.title) for key, definition in ENCOUNTER_DEFINITIONS.items()
        if definition.kind == 'battle'])

    class Meta:
        model = EncounterMonster
        fields = '__all__'


@admin.register(EncounterMonster)
class EncounterMonsterAdmin(admin.ModelAdmin):
    form = CompositionForm
    list_display = ('encounter_definition_key', 'monster', 'quantity', 'position_order')
    list_filter = ('encounter_definition_key',)
    ordering = ('encounter_definition_key', 'position_order')
