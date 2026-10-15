from django.urls import path
from . import views

urlpatterns = [
    path("<int:item_id>/", views.item_detail, name="item_detail"),
    path("<int:item_id>/use/", views.use_item_api, name="use_item_api"),
    path("unequip/<str:slot_type>/", views.unequip_item_api, name="unequip_item_api"),
    path("inventory/", views.inventory_view, name="inventory"),
]
