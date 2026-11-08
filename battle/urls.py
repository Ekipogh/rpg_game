from django.urls import path
from . import views

app_name = 'battle'
urlpatterns = [
    path('<int:battle_id>/state/', views.state_view, name='state'),
    path('<int:battle_id>/events/', views.events_view, name='events'),
    path('<int:battle_id>/commands/', views.commands_view, name='commands'),
]
