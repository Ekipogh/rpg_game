from django.urls import path
from . import views

urlpatterns = [
    path('dungeon/', views.dungeon_view, name='dungeon'),
    path('dungeon/fight/', views.dungeon_view, {'encounter_kind': 'fight'}, name='dungeon_fight'),
    path('dungeon/treasure/', views.dungeon_view, {'encounter_kind': 'treasure'}, name='dungeon_treasure'),
    path('dungeon/trap/', views.dungeon_view, {'encounter_kind': 'trap'}, name='dungeon_trap'),
    path('dungeon/npc/', views.dungeon_view, {'encounter_kind': 'npc'}, name='dungeon_npc'),
    path('dungeon/action/', views.dungeon_action_view, name='dungeon_action'),
    path('home/', views.home_view, name='home'),
    path('create-character/', views.character_creation_view,
         name='create_character'),
    path('', views.index, name='index'),
    path('select-hero/', views.hero_selection_view, name='hero_selection'),
    path('select-hero/<int:hero_id>/', views.select_hero, name='select_hero'),
    path('delete-hero/<int:hero_id>/', views.delete_hero, name='delete_hero')
]
