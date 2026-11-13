"""
URL configuration for game project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from .health import health
from django.urls import include, path
from item.views import inventory_view  # Import the inventory view directly
from item import shop_views

urlpatterns = [
    path('shop/', shop_views.shop_view, name='shop'),
    path('shop/buy/<int:target_id>/', shop_views.trade, {'action': 'buy'}, name='shop_buy'),
    path('shop/sell/<int:target_id>/', shop_views.trade, {'action': 'sell'}, name='shop_sell'),
    path('health/', health, name='health'),
    path('admin/', admin.site.urls),
    path('', include('hero.urls')),
    path('item/', include('item.urls')),
    path('battle/', include('battle.urls')),
    path('unicorn/', include('django_unicorn.urls')),
    path('inventory/', inventory_view, name='inventory'),  # Direct route to inventory
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
