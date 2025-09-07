from django.urls import path
from . import views

urlpatterns = [
    path('home/', views.home_view, name='home'),
    path('create-character/', views.character_creation_view,
         name='create_character'),
    path('', views.index, name='index'),
    path('select-hero/', views.hero_selection_view, name='hero_selection'),
    path('select-hero/<int:hero_id>/', views.select_hero, name='select_hero')
]
