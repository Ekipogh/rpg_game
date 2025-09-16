from django.shortcuts import render, redirect

from hero.models import HeroClass, Hero

# Create your views here.


def home_view(request):
    hero_id = request.session.get('hero_id')
    hero = Hero.objects.filter(id=hero_id).first() if hero_id else None
    if not hero:
        return redirect('index')
    return render(request, 'hero/home.html', {'hero': hero})


def character_creation_view(request):
    classes = HeroClass.objects.all()
    return render(request, 'hero/character_creation.html', {'hero_classes': classes})


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
        classes = HeroClass.objects.all()
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
