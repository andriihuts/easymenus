from rest_framework import viewsets, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import MenuCategory, MenuItem, Menu
from django.core.exceptions import PermissionDenied

# Category API Views
@api_view(['GET', 'PUT', 'DELETE'])
def category_detail(request, category_id):
    category = get_object_or_404(MenuCategory, id=category_id)
    
    # Check if user owns this category
    if category.menu.user != request.user:
        raise PermissionDenied
    
    if request.method == 'GET':
        data = {
            'id': category.id,
            'name': category.name,
            'name_secondary': category.name_secondary,
            'order': category.order
        }
        return Response(data)
    
    elif request.method == 'PUT':
        category.name = request.data.get('name', category.name)
        category.name_secondary = request.data.get('name_secondary', category.name_secondary)
        category.order = request.data.get('order', category.order)
        category.save()
        return Response({'status': 'updated'})
    
    elif request.method == 'DELETE':
        category.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# Menu Item API Views
@api_view(['GET', 'PUT', 'DELETE'])
def menu_item_detail(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id)
    
    # Check if user owns this item
    if item.menu.user != request.user:
        raise PermissionDenied
    
    if request.method == 'GET':
        data = {
            'id': item.id,
            'title': item.title,
            'title_secondary': item.title_secondary,
            'description': item.description,
            'description_secondary': item.description_secondary,
            'cost': str(item.cost),  # Convert Decimal to string
            'order': item.order,
            'options': item.options
        }
        return Response(data)
    
    elif request.method == 'PUT':
        item.title = request.data.get('title', item.title)
        item.title_secondary = request.data.get('title_secondary', item.title_secondary)
        item.description = request.data.get('description', item.description)
        item.description_secondary = request.data.get('description_secondary', item.description_secondary)
        
        # Handle cost carefully since it's a Decimal
        if 'cost' in request.data:
            item.cost = request.data['cost']
            
        item.order = request.data.get('order', item.order)
        item.options = request.data.get('options', item.options)
        item.save()
        return Response({'status': 'updated'})
    
    elif request.method == 'DELETE':
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# Menu Order Updates
@api_view(['POST'])
def update_menu_order(request, menu_id):
    menu = get_object_or_404(Menu, id=menu_id, user=request.user)
    
    # Expecting data in the format:
    # {
    #   "categories": [
    #     {
    #       "id": 1,
    #       "order": 0,
    #       "items": [{"id": 1, "order": 0}, {"id": 2, "order": 1}]
    #     }
    #   ]
    # }
    
    try:
        for cat_data in request.data.get('categories', []):
            category = MenuCategory.objects.get(id=cat_data['id'], menu=menu)
            category.order = cat_data['order']
            category.save()
            
            # Update items order within category
            for item_data in cat_data.get('items', []):
                item = MenuItem.objects.get(id=item_data['id'], menu=menu)
                item.order = item_data['order']
                item.category = category  # Update category in case item was moved
                item.save()
                
        return Response({'status': 'success'})
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )