from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from hero.models import Hero
from .models import Item
from . import shop


@require_GET
def shop_view(request):
    hero = Hero.objects.filter(pk=request.session.get('hero_id')).first()
    if not hero:
        return redirect('index')
    state = shop.stock_for(hero)
    hero.refresh_from_db()
    offers = []
    for offer in state.offers.all():
        item = Item.objects.get(pk=offer.item_id)
        reason = ('Shopping is unavailable during combat.' if hero.is_in_combat else
                  'Sold out.' if not offer.remaining else
                  'Item no longer available.' if not shop.eligible(item, hero) else
                  'Not enough money.' if hero.money < offer.price else '')
        offers.append({'offer': offer, 'item': item, 'reason': reason})
    sales = []
    if hero.inventory_id:
        for entry in hero.inventory.all().filter(quantity__gt=0):
            price = max(0, entry.item.value // 2)
            sales.append({'stock': entry, 'price': price, 'reason':
                'Shopping is unavailable during combat.' if hero.is_in_combat else
                'This item has no sale value.' if not price else ''})
    return render(request, 'item/shop.html', {'hero': hero, 'shop': state, 'offers': offers, 'sales': sales})


@require_POST
def trade(request, action, target_id):
    hero = Hero.objects.filter(pk=request.session.get('hero_id')).first()
    if not hero:
        return redirect('index')
    try:
        {'buy': shop.buy, 'sell': shop.sell}[action](hero, target_id, request.POST.get('quantity', '1'))
    except ValueError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, 'Purchase complete.' if action == 'buy' else 'Sale complete.')
    return redirect('shop')
