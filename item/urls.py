from django.urls import path
from . import views

urlpatterns = [
    path("<int:item_id>/", views.item_detail, name="item_detail"),
    path("<int:item_id>/use/", views.use_item_api, name="use_item_api"),
]
