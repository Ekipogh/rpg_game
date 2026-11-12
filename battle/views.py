"""Session-scoped battle reads and command submission."""
import json
from uuid import UUID

from django.db import OperationalError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import Battle, BattleWorkerLease
from .services import BattleConflict, LEASE_NAME, submit_command, loot_report
from .engine import CombatStats, BattleRules, attack_interval_ms
from item.models import Consumable, Instant, InventoryItem


def selected_battle(request, battle_id):
    return get_object_or_404(Battle, pk=battle_id, hero_id=request.session.get('hero_id'))


def pagination(request):
    after = int(request.GET.get('after_seq', '0'))
    limit = int(request.GET.get('limit', '100'))
    if after < 0 or not 1 <= limit <= 100:
        raise ValueError('Invalid event cursor or limit')
    return after, limit


def event_page(battle, after, limit):
    rows = list(battle.events.filter(sequence__gt=after, sequence__lte=battle.last_event_sequence)
        .order_by('sequence').values('sequence', 'simulation_time_ms', 'event_type',
                                    'actor_id', 'target_id', 'payload')[:limit])
    cursor = rows[-1]['sequence'] if rows else after
    return {'events': rows, 'next_seq': cursor, 'has_more': cursor < battle.last_event_sequence}


def receipt(command):
    return {'id': str(command.pk), 'sequence': command.sequence, 'status': command.status,
            'reason': command.reject_reason, 'execute_at_ms': command.execute_at_ms}


@never_cache
@ensure_csrf_cookie
@require_GET
def state_view(request, battle_id):
    # A transaction keeps the checkpoint/cursors and log page from different commits apart.
    with transaction.atomic():
        battle = selected_battle(request, battle_id)
        try:
            after, limit = pagination(request)
        except ValueError as exc:
            return JsonResponse({'error': str(exc)}, status=400)
        state, snapshot = battle.checkpoint or {}, battle.snapshot or {}
        actors = []
        for definition in snapshot.get('combatants', []):
            actor = state.get('combatants', {}).get(definition['combatant_id'])
            if actor is None:
                continue
            stats = definition['stats']
            actors.append({**actor, 'name': definition['name'], 'team': definition['team'],
                'attack_range_min': definition['attack_range_min'],
                'attack_range_max': definition['attack_range_max'],
                'max_health': stats['max_health'], 'max_mana': stats['max_mana'],
                'attack_interval_ms': attack_interval_ms(CombatStats(**stats), BattleRules(**snapshot['rules']))})
        lease = BattleWorkerLease.objects.filter(name=LEASE_NAME).first()
        result = state.get('outcome')
        if result is not None:
            money_change = sum(payload.get('money_change', 0) for payload in
                battle.events.filter(event_type='instant_use').values_list('payload', flat=True))
            result = {**result, 'loot': loot_report(result.get('loot', [])), 'money_change': money_change}
        available = bool(lease and lease.owner_token and lease.expires_at and lease.expires_at > timezone.now())
        items = []
        for stock in InventoryItem.objects.filter(inventory_id=battle.hero.inventory_id, quantity__gt=0).select_related('item'):
            item = stock.item.get_real_instance()
            if isinstance(item, Consumable) and not isinstance(item, Instant):
                items.append({'id': item.pk, 'name': item.name, 'quantity': stock.quantity,
                    'heal_amount': item.heal_amount, 'mana_restore': item.mana_restore,
                    'use_url': reverse('use_item_api', args=[item.pk])})
        data = {'id': battle.pk, 'revision': battle.revision, 'status': battle.status,
            'items': items,
            'simulation_time_ms': state.get('simulation_time_ms', 0), 'combatants': actors,
            'lane_count': snapshot.get('rules', {}).get('lane_count', 9),
            'last_event_sequence': battle.last_event_sequence, 'worker_available': available,
            'outcome': battle.outcome,
            'result': result,
            'error': 'This fight is paused. Please contact the game administrator.' if battle.status == 'PAUSED_ERROR' else None,
            'next_url': reverse('dungeon') if battle.outcome == 'VICTORY' and snapshot.get('battle_tier') != 'boss' else reverse('home'),
            'commands': [receipt(c) for c in battle.commands.order_by('-sequence')[:100]],
            **event_page(battle, after, limit)}
    return JsonResponse(data)


@never_cache
@require_GET
def events_view(request, battle_id):
    battle = selected_battle(request, battle_id)
    try:
        after, limit = pagination(request)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    if 'before_seq' in request.GET:
        try:
            before = int(request.GET['before_seq'])
            if before < 1:
                raise ValueError
        except ValueError:
            return JsonResponse({'error': 'Invalid older-event cursor'}, status=400)
        rows = list(battle.events.filter(sequence__lt=before, sequence__lte=battle.last_event_sequence)
            .order_by('-sequence').values('sequence', 'simulation_time_ms', 'event_type',
                                        'actor_id', 'target_id', 'payload')[:limit])
        rows.reverse()
        return JsonResponse({'events': rows, 'has_older': bool(rows and rows[0]['sequence'] > 1)})
    return JsonResponse(event_page(battle, after, limit))


@never_cache
@require_POST
def commands_view(request, battle_id):
    selected_battle(request, battle_id)
    try:
        if len(request.body) > 4096:
            raise ValueError('Command is too large')
        body = json.loads(request.body)
        if type(body) is not dict or set(body) != {'id', 'command_type', 'payload'}:
            raise ValueError('Invalid command fields')
        command_id = UUID(body['id']) if type(body['id']) is str else None
        if command_id is None or type(body['command_type']) is not str or type(body['payload']) is not dict:
            raise ValueError('Invalid command')
        command, created = submit_command(battle_id, request.session.get('hero_id'),
            command_id, body['command_type'], body['payload'])
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except BattleConflict as exc:
        return JsonResponse({'error': str(exc)}, status=409)
    except Battle.DoesNotExist:
        return JsonResponse({'error': 'Battle unavailable'}, status=404)
    except OperationalError:
        return JsonResponse({'error': 'Battle is busy; retry this command.'}, status=503)
    return JsonResponse(receipt(command), status=202 if created else 200)
