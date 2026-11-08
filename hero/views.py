from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponseBadRequest
from django.views.decorators.http import require_GET, require_POST
from .dungeon import apply_action
from .encounters import Encounter
from battle.models import Battle

from hero.models import HeroClass, Hero

# Create your views here.


def home_view(request):
    hero_id = request.session.get('hero_id')
    hero = Hero.objects.filter(id=hero_id).first() if hero_id else None
    if not hero:
        return redirect('index')
    if hero.dungeon_run:
        return redirect('dungeon')
    return render(request, 'hero/home.html', {'hero': hero})


def character_creation_view(request):
    return render(request, 'hero/character_creation.html', {'hero_classes': HeroClass.objects.all()})


def hero_selection_view(request):
    heroes = Hero.objects.all()
    return render(request, 'hero/hero_selection.html', {'heroes': heroes})


def index(request):
    # if a hero is created, redirect to hero selection
    # else redirect to character creation
    hero = Hero.objects.first()
    if hero:
        return redirect('hero_selection')
    else:
        return redirect('create_character')


def select_hero(request, hero_id):
    hero = Hero.objects.get(id=hero_id)
    request.session['hero_id'] = hero.id
    return redirect('home')


def delete_hero(request, hero_id):
    hero = Hero.objects.get(id=hero_id)
    hero.delete()
    # If the deleted hero was the current session hero, clear it
    if request.session.get('hero_id') == hero_id:
        request.session.pop('hero_id', None)
    return redirect('hero_selection')


@require_GET
def dungeon_view(request, encounter_kind=None):
    hero = Hero.objects.filter(pk=request.session.get('hero_id')).first()
    if not hero:
        return redirect('index')
    if not hero.dungeon_run:
        return redirect('home')
    run = hero.dungeon_run
    encounter = Encounter.from_dict(run['current_encounter'])
    page = 'fight' if encounter.kind == 'battle' else encounter.kind
    if run['phase'] == 'encounter':
        if encounter_kind != page:
            return redirect('dungeon_' + page)
        template = f'hero/encounters/{page}.html'
    else:
        if encounter_kind is not None:
            return redirect('dungeon')
        template = 'hero/dungeon.html'
    return render(request, template, {
        'hero_id': hero.pk, 'hero_name': hero.name, 'health': hero.current_health,
        'max_health': hero.max_health, 'mana': hero.current_mana, 'max_mana': hero.max_mana,
        'floor': run['current_floor'], 'phase': run['phase'],
        'result': run['last_result'], 'revision': hero.dungeon_revision,
        'title': encounter.definition.title, 'description': encounter.definition.description,
        'is_battle': encounter.kind == 'battle',
        'battle': Battle.objects.filter(hero=hero, encounter_id=encounter.id).first()
                  if encounter.kind == 'battle' else None,
    })


@require_POST
def dungeon_action_view(request):
    selected_hero_id = request.session.get('hero_id')
    hero = Hero.objects.filter(pk=selected_hero_id).first() if selected_hero_id else None
    if not hero:
        return redirect('index')
    try:
        originating_hero_id = int(request.POST['hero_id'])
        revision = int(request.POST['revision'])
        raw_choice = request.POST.get('choice')
        if raw_choice is not None and raw_choice not in ('0', '1'):
            raise ValueError
        choice = int(raw_choice) if raw_choice is not None else None
    except (KeyError, ValueError):
        return HttpResponseBadRequest('Invalid dungeon action.')
    if originating_hero_id != hero.pk:
        return HttpResponseBadRequest('Invalid dungeon action.')
    outcome = apply_action(hero.pk, request.POST.get('action'), revision, choice)
    if outcome == 'invalid':
        return HttpResponseBadRequest('Invalid dungeon action.')
    if outcome in ('retreat', 'defeat'):
        messages.info(request, 'You retreated with your remaining HP and earned XP.'
                      if outcome == 'retreat' else 'You were defeated and returned home with 1 HP.')
        return redirect('home')
    if outcome == 'stale':
        messages.info(request, 'Your dungeon progress changed. The latest state is shown.')
    return redirect('dungeon')
