from django.shortcuts import render

# Create your views here.

def item_detail(request, item_id):
    return render(request, 'item/detail.html', {'item_id': item_id})
