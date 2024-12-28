from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.contrib import messages
from .models import Menu, MenuItem
from .forms import MenuItemForm
from django.urls import reverse
from urllib.parse import urlencode
from django.http import HttpResponseBadRequest
from django.template.loader import render_to_string
from django.shortcuts import redirect
import cloudinary
import cloudinary.uploader
import cloudinary.api
from django.views.decorators.csrf import csrf_exempt
import json
from urllib.parse import unquote
from django.db import transaction
from django.conf import settings  # Add this import

# Add these imports
from .utils.gpt_processing import process_images_with_gpt, process_menu_image, get_user_media_library
from .utils.parser import populate_menu_from_json
import logging

logger = logging.getLogger(__name__)

from .models import (
    Subscription,
    Menu,
    MenuImage,
    MenuCategory,
    MenuItem,
    Template,
    PublishedMenu,
    TemplateAnalytics,
    MenuTemplate,
)

from .forms import (
    SignUpForm,
    EmailAuthenticationForm,
    BusinessProfileUpdateForm,
    SubscriptionUpdateForm,
    # Remove MenuForm since we're not using it
    MenuImageUploadForm,
    MenuCreationForm,  # This is the correct name now
    MenuProcessingForm,
    CategoryForm,
    MenuItemForm,
    TemplateCustomizationForm,
    DomainSettingsForm,
    PublishMenuForm,

)

# API Views
@api_view(['GET'])
def example_api(request):
    return Response({'message': 'Hello, headless Django!'})

def home(request):
    return render(request, 'static/home.html')

def about(request):
    return render(request, 'static/about.html')

def features(request):
    return render(request, 'static/features.html')

def pricing(request):
    return render(request, 'static/pricing.html')

def contact(request):
    return render(request, 'static/contact.html')

def verify_password(request):
    if request.method == 'POST':
        if request.POST.get('password') == settings.SITE_PASSWORD:
            request.session['password_verified'] = True
            return redirect('home')
    return render(request, 'myapp/verify_password.html')

def custom_404(request, exception):
    return render(request, '404.html', status=404)

def all_menus(request, menu_id=None):
    menus = Menu.objects.filter(user=request.user)
    
    # Handle menu creation
    if request.method == 'POST' and 'menu_name' in request.POST:
        menu_name = request.POST.get('menu_name').strip()
        if menu_name:
            menu = Menu.objects.create(
                user=request.user,
                name=menu_name,
                menu_data={"items": []}
            )
            messages.success(request, f"Menu '{menu_name}' created successfully!")
            return redirect(f'{reverse("all_menus")}?menu_id={menu.id}')
    
    # Get selected menu (either from URL parameter or request GET parameter)
    selected_menu_id = menu_id or request.GET.get('menu_id')
    selected_menu = None
    items = None
    categories = None

    # If no menu is selected, try to get the first menu
    if not selected_menu_id and menus.exists():
        selected_menu = menus.first()
    elif selected_menu_id:
        try:
            selected_menu = Menu.objects.get(id=selected_menu_id, user=request.user)
        except Menu.DoesNotExist:
            if menus.exists():
                selected_menu = menus.first()
            messages.error(request, "Menu not found.")

    # If we have a selected menu, get its items and categories
    if selected_menu:
        items = selected_menu.menuitem_set.all()
        categories = selected_menu.categories.all()
        
        # Ensure the menu has a default category
        selected_menu.ensure_default_category()

    context = {
        'menus': menus,
        'selected_menu': selected_menu,
        'categories': categories,
        'items': items,
        'item_form': MenuItemForm(user=request.user, menu=selected_menu) if selected_menu else None,
    }
    
    return render(request, 'myapp/all_menus.html', context)




@login_required
def view_menu(request, menu_id):
    selected_menu = get_object_or_404(Menu, id=menu_id, user=request.user)
    categories = selected_menu.categories.prefetch_related('menuitem_set')

    # Build the context with proper model data
    context = {
        'selected_menu': selected_menu,
        'categories': categories,  # This uses related model data
    }
    return render(request, 'myapp/view_menu.html', context)


# Authentication Views
def signup_view(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            menu = Menu.objects.create(
                user=user,
                menu_data={"items":[]},
                name=user.business_name
            )
            login(request, user)
            return redirect('dashboard')
    else:
        form = SignUpForm()
    return render(request, 'myapp/signup.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = EmailAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
    else:
        form = EmailAuthenticationForm()
    return render(request, 'myapp/login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('login')

# Dashboard Views
@login_required
def dashboard_view(request):
    subscription = getattr(request.user, 'subscription', None)
    if subscription is None:
        subscription = Subscription.objects.create(user=request.user)

    subscription.reset_monthly_processings()

    if request.method == 'POST':
        if 'level' in request.POST or 'billing_cycle' in request.POST:
            # Subscription form handling
            sub_form = SubscriptionUpdateForm(request.POST, instance=subscription)
            profile_form = BusinessProfileUpdateForm(instance=request.user)
            if sub_form.is_valid():
                sub = sub_form.save(commit=False)
                sub.end_date = timezone.now() + timedelta(
                    days=365 if sub.billing_cycle == 'yearly' else 30
                )
                sub.save()
                return redirect('dashboard')
        else:
            # Profile form handling
            profile_form = BusinessProfileUpdateForm(request.POST, instance=request.user)
            sub_form = SubscriptionUpdateForm(instance=subscription)
            if profile_form.is_valid():
                profile_form.save()
                return redirect('dashboard')
    else:
        sub_form = SubscriptionUpdateForm(instance=subscription)
        profile_form = BusinessProfileUpdateForm(instance=request.user)

    context = {
        'subscription': subscription,
        'sub_form': sub_form,
        'profile_form': profile_form,
        'processings_remaining': (
            'Unlimited' if subscription.level == 'premium' 
            else subscription.monthly_processing_limit - subscription.processings_this_month
        ),
        'total_processings': subscription.total_processings,
        'processings_this_month': subscription.processings_this_month,
        'processing_limit': subscription.monthly_processing_limit or 'Unlimited',
    }
    return render(request, 'myapp/dashboard.html', context)

# Menu Management Views
@login_required
def scan_view(request):
    menus = Menu.objects.filter(user=request.user)
    active_menu = menus.filter(is_active=True).first()
    
    images = MenuImage.objects.filter(
        user=request.user,
        image_type='menu'
    ).order_by('-uploaded_at')
    
    active_menu = menus.filter(is_active=True).first()
    
    context = {
        'menus': menus,
        'images': images,
        'active_menu': active_menu,
        'menu_form': MenuCreationForm(),
        'image_form': MenuImageUploadForm(),
        'processing_form': MenuProcessingForm(user=request.user),
    }
    
    if request.method == 'POST':
        if 'switch_menu' in request.POST:
            menu_id = request.POST.get('menu_id')
            if menu_id:
                Menu.objects.filter(user=request.user).update(is_active=False)
                Menu.objects.filter(id=menu_id, user=request.user).update(is_active=True)
                return redirect('scan_page')
    
    return render(request, 'myapp/scan.html', context)

@login_required
def upload_image(request):
    if request.method == 'POST':
        for image_file in request.FILES.getlist('image'):
            try:
                # Upload to Cloudinary with menu-specific tags
                upload_result = cloudinary.uploader.upload(
                    image_file,
                    folder=f"menu_images/user_{request.user.id}",
                    tags=[f"user_{request.user.id}", "menu_item"],  # Specific menu tag
                    context={
                        "user_id": str(request.user.id),
                        "type": "menu_item"
                    }
                )
                name = request.POST.get(f'name_{image_file.name}', '')

                # Create MenuImage record
                MenuImage.objects.create(
                    user=request.user,
                    image=upload_result['public_id'],
                    public_id=upload_result['public_id'],
                    image_type='menu',  # Explicitly set as menu type
                    name=name,
                )
                
            except Exception as e:
                print(f"Error uploading image: {str(e)}")
                return JsonResponse({'success': False, 'error': str(e)})
                
        return JsonResponse({'success': True})
    return JsonResponse({'success': False})

@login_required
def process_image(request):
    if request.method == 'POST':
        image_id = request.POST.get('image_id')
        action = request.POST.get('action', 'new')
        
        try:
            menu_image = MenuImage.objects.get(id=image_id, user=request.user)
            
            # Process the image with GPT and get menu data
            result = process_menu_image(menu_image.get_cloudinary_url(), request.user)
            
            # Debug logging to see the exact structure
            logger.debug(f"Raw result from process_menu_image: {result}")
            
            if not result:
                messages.error(request, "Failed to process menu image.")
                return redirect('scan_page')
            
            # Check if result is already in the correct format
            if isinstance(result, dict) and 'menu_categories' in result:
                menu_data = result
            else:
                # Try to extract menu data from different possible structures
                menu_data = result.get('menu_data', {})
                if not menu_data and isinstance(result, list):
                    # If result is a list of categories
                    menu_data = {"menu_categories": result}
                elif not menu_data and isinstance(result, dict):
                    # If result is already in the right structure but without wrapper
                    menu_data = {"menu_categories": [result]}
            
            logger.debug(f"Structured menu_data: {menu_data}")
            
            if not menu_data or not menu_data.get('menu_categories'):
                messages.error(request, "No menu data was extracted from the image.")
                logger.error(f"Menu data extraction failed. Result structure: {result}")
                return redirect('scan_page')
            
            if action == 'new':
                # Create new menu
                menu_name = request.POST.get('menu_name', 'Untitled Menu')
                menu = Menu.objects.create(
                    name=menu_name,
                    user=request.user
                )
                populate_menu_from_json(menu, menu_data, action='new')
                messages.success(request, f"Created new menu: {menu_name}")
                
            else:
                # Get existing menu for 'existing' or 'add' actions
                existing_menu_id = request.POST.get('existing_menu')
                if not existing_menu_id:
                    messages.error(request, "No menu selected.")
                    return redirect('scan_page')
                    
                menu = get_object_or_404(Menu, id=existing_menu_id, user=request.user)
                
                if action == 'existing':
                    # Replace existing menu
                    populate_menu_from_json(menu, menu_data, action='existing')
                    messages.success(request, f"Updated menu: {menu.name}")
                else:  # action == 'add'
                    # Add to existing menu
                    populate_menu_from_json(menu, menu_data, action='add')
                    messages.success(request, f"Added items to menu: {menu.name}")
            
            return redirect('all_menus', menu_id=menu.id)
            
        except MenuImage.DoesNotExist:
            messages.error(request, "Menu image not found.")
            logger.error("Menu image not found")
        except Exception as e:
            logger.error(f"Error processing menu image: {str(e)}", exc_info=True)
            messages.error(request, f"Error processing menu image: {str(e)}")
    
    return redirect('scan_page')

@login_required
def update_menu_order(request):
    if request.method == 'POST':
        try:
            order = request.JSON.loads(request.body)['order']
            # Update menu item order in the database
            # Implementation needed here
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@login_required
def edit_item(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id, menu__user=request.user)
    menu = item.menu
    page = int(request.GET.get('page', 1))
    items_per_page = 50

    if request.method == 'POST':
        form = MenuItemForm(request.POST, instance=item, user=request.user, menu=menu)
        if form.is_valid():
            try:
                item = form.save(commit=False)
                item.menu = menu
                item.save()
                
                selected_image_ids = form.cleaned_data.get('media_library', [])
                item.images.clear()
                
                for public_id in selected_image_ids:
                    menu_image = MenuImage.objects.get(
                        user=request.user,
                        public_id=public_id
                    )
                    item.images.add(menu_image)
                
                messages.success(request, "Item updated successfully.")
                return redirect(f'{reverse("all_menus")}?menu_id={item.menu.id}')
            except Exception as e:
                logger.error(f"Error saving item: {str(e)}")
                messages.error(request, f"Error saving item: {str(e)}")
    else:
        form = MenuItemForm(instance=item, user=request.user, menu=menu)

    try:
        # Get total count and paginate
        all_images = MenuImage.objects.filter(
            user=request.user,
            image_type='general'
        ).order_by('-id')
        
        total_images = all_images.count()
        total_pages = (total_images + items_per_page - 1) // items_per_page
        
        # Get current page's images
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        current_page_images = all_images[start_idx:end_idx]
        
        # Get public IDs for current page
        public_ids = [img.public_id for img in current_page_images if img.public_id]
        
        media_images = []
        if public_ids:
            resources = cloudinary.api.resources_by_ids(
                public_ids,
                context=True,
                tags=True,
            )
            
            for img in resources.get('resources', []):
                media_images.append({
                    'url': img['secure_url'],
                    'public_id': img['public_id'],
                    'version': img.get('version', ''),
                    'selected': item.images.filter(public_id=img['public_id']).exists()
                })

        # Pagination context
        pagination = {
            'current_page': page,
            'total_pages': total_pages,
            'has_previous': page > 1,
            'has_next': page < total_pages,
            'previous_page': page - 1,
            'next_page': page + 1,
            'page_range': range(max(1, page - 2), min(total_pages + 1, page + 3)),
        }

    except Exception as e:
        logger.error(f"Error fetching media images: {str(e)}")
        media_images = []
        pagination = None

    return render(request, 'myapp/edit_item.html', {
        'form': form,
        'item': item,
        'media_images': media_images,
        'pagination': pagination,
    })


@login_required
def delete_item(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id, menu__user=request.user)
    menu = item.menu  # Get the associated menu

    if request.method == 'POST':
        item.delete()
        messages.success(request, "Item deleted successfully.")
        # Redirect back to the current menu page
        return redirect(f'{reverse("all_menus")}?menu_id={menu.id}')

    return render(request, 'myapp/delete_item.html', {'item': item})


@login_required
def add_category(request, menu_id):
    menu = get_object_or_404(Menu, id=menu_id, user=request.user)

    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.menu = menu

            # Set a default order if not provided
            category.order = menu.categories.count() + 1
            category.save()

            # Redirect to all_menus.html with the current menu context
            return render(request, 'myapp/all_menus.html', {
                'menus': Menu.objects.filter(user=request.user),
                'selected_menu': menu,
                'categories': menu.categories.all(),
                'items': menu.menuitem_set.all(),
            })
        else:
            # If the form is invalid, re-render the same page with errors
            return render(request, 'myapp/all_menus.html', {
                'menus': Menu.objects.filter(user=request.user),
                'selected_menu': menu,
                'categories': menu.categories.all(),
                'items': menu.menuitem_set.all(),
                'form_errors': form.errors,
            })

    # Handle non-POST requests gracefully
    return redirect('all_menus')

@login_required
def add_item(request, menu_id):
    menu = get_object_or_404(Menu, id=menu_id, user=request.user)

    if request.method == 'POST':
        form = MenuItemForm(request.POST, menu=menu)  # Pass the menu object explicitly
        if form.is_valid():
            item = form.save(commit=False)
            item.menu = menu
            item.save()
            messages.success(request, "Item added successfully!")
            # Redirect to the current menu page
            return redirect(f'{reverse("all_menus")}?menu_id={menu.id}')
        else:
            messages.error(request, "Error adding item. Please check the form.")

    # Pass the menu explicitly here too
    form = MenuItemForm(menu=menu)
    return render(request, 'myapp/add_item.html', {'form': form, 'menu': menu})

@login_required
def delete_category(request, category_id):
    category = get_object_or_404(MenuCategory, id=category_id, menu__user=request.user)

    if not category.deletable:
        messages.error(request, "The 'Default' category cannot be deleted.")
        return redirect(f'{reverse("all_menus")}?menu_id={category.menu.id}')

    if request.method == 'POST':
        menu = category.menu
        # Re-fetch the default category
        default_category = menu.categories.filter(default=True).first()

        if not default_category:
            # Ensure default category exists before proceeding
            menu.ensure_default_category()
            default_category = menu.categories.filter(default=True).first()

        if not default_category:
            messages.error(request, "Default category not found. Please ensure the menu has a default category.")
            return redirect(f'{reverse("all_menus")}?menu_id={menu.id}')

        # Reassign items to the default category
        MenuItem.objects.filter(category=category).update(category=default_category)

        # Delete the category
        category.delete()

        # Optionally reorder the remaining categories
        for index, cat in enumerate(menu.categories.order_by('order')):
            cat.order = index + 1
            cat.save()

        messages.success(request, "Category deleted successfully!")
        return redirect(f'{reverse("all_menus")}?menu_id={menu.id}')

    messages.error(request, "Invalid request method.")
    return redirect('all_menus')



@login_required
def edit_category(request, category_id):
    category = get_object_or_404(MenuCategory, id=category_id, menu__user=request.user)
    page = int(request.GET.get('page', 1))
    items_per_page = 50

    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category, user=request.user)
        if form.is_valid():
            try:
                category = form.save()
                messages.success(request, "Category updated successfully!")
                return redirect(f'{reverse("all_menus")}?menu_id={category.menu.id}')
            except Exception as e:
                logger.error(f"Error saving category: {str(e)}")
                messages.error(request, f"Error saving category: {str(e)}")
        else:
            messages.error(request, "Error updating category. Please check the form.")
            logger.error(f"Form errors: {form.errors}")
    else:
        form = CategoryForm(instance=category, user=request.user)

    try:
        # Get total count and paginate
        all_images = MenuImage.objects.filter(
            user=request.user,
            image_type='general'
        ).order_by('-id')
        
        total_images = all_images.count()
        total_pages = (total_images + items_per_page - 1) // items_per_page
        
        # Get current page's images
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        current_page_images = all_images[start_idx:end_idx]
        
        # Get public IDs for current page
        public_ids = [img.public_id for img in current_page_images if img.public_id]
        
        media_images = []
        if public_ids:
            resources = cloudinary.api.resources_by_ids(
                public_ids,
                context=True,
                tags=True,
            )
            
            for img in resources.get('resources', []):
                media_images.append({
                    'url': img['secure_url'],
                    'public_id': img['public_id'],
                    'version': img.get('version', ''),
                    'selected': category.images.filter(public_id=img['public_id']).exists()
                })

        # Pagination context
        pagination = {
            'current_page': page,
            'total_pages': total_pages,
            'has_previous': page > 1,
            'has_next': page < total_pages,
            'previous_page': page - 1,
            'next_page': page + 1,
            'page_range': range(max(1, page - 2), min(total_pages + 1, page + 3)),
        }

    except Exception as e:
        logger.error(f"Error fetching media images: {str(e)}")
        media_images = []
        pagination = None

    return render(request, 'myapp/edit_category.html', {
        'form': form,
        'category': category,
        'media_images': media_images,
        'pagination': pagination,
    })


@login_required
def rename_menu(request, menu_id):
    menu = get_object_or_404(Menu, id=menu_id, user=request.user)

    if request.method == 'POST':
        new_name = request.POST.get('name', '').strip()
        if new_name:
            menu.name = new_name
            menu.save()
            messages.success(request, "Menu renamed successfully.")
            return redirect(f'{reverse("all_menus")}?menu_id={menu.id}')
        else:
            messages.error(request, "Menu name cannot be empty.")

    return redirect(f'{reverse("all_menus")}?menu_id={menu.id}')

@login_required
def delete_menu(request, menu_id):
    menu = get_object_or_404(Menu, id=menu_id, user=request.user)

    if request.method == 'POST':
        menu.delete()
        messages.success(request, "Menu deleted successfully.")
        return redirect('all_menus')

    messages.error(request, "Invalid request method.")
    return redirect('all_menus')

def get_active_menu(user):
    # Replace with your logic to fetch the active menu
    # For example, if you have a field in your User model:
    return user.active_menu 

@login_required
def media_library(request):
    page = int(request.GET.get('page', 1))
    items_per_page = 50  # We can adjust this number

    search_query = request.GET.get('search', '')

    
    try:
        logger.debug("Fetching images from Cloudinary")
        
        
        base_query = MenuImage.objects.filter(
            user=request.user,
            image_type='general'
        )
        
        # Apply search filter if query exists
        if search_query:
            base_query = base_query.filter(name__icontains=search_query)

        # Get all public IDs from the database
        all_images = MenuImage.objects.filter(
            user=request.user,
            image_type='general'
        ).values_list('public_id', flat=True).order_by('-id')  # Order by newest first
        
        # Calculate pagination
        total_images = len(all_images)
        total_pages = (total_images + items_per_page - 1) // items_per_page
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        
        # Get current page's images
        current_page_images = list(all_images[start_idx:end_idx])
        
        logger.debug(f"Processing page {page} with {len(current_page_images)} images")
        
        user_images = []
        if current_page_images:
            try:
                resources = cloudinary.api.resources_by_ids(
                    current_page_images,
                    context=True,
                    tags=True,
                )
                
                # Get corresponding MenuImage objects to access their names
                menu_images = {
                    img.public_id: img for img in base_query.filter(
                        public_id__in=current_page_images
                    )
                }
                
                for img in resources.get('resources', []):
                    menu_image = menu_images.get(img['public_id'])
                    user_images.append({
                        'url': img['secure_url'],
                        'public_id': img['public_id'],
                        'version': img.get('version', ''),
                        'context': img.get('context', {}),
                        'format': img.get('format', ''),
                        'tags': img.get('tags', []),
                        'name': menu_image.name if menu_image else '',
                        'id': menu_image.id if menu_image else None
                    })
                    
            except Exception as e:
                logger.error(f"Error fetching images from Cloudinary: {str(e)}")
                messages.error(request, "Error loading images from cloud storage")
        
        # Pagination context
        pagination = {
            'current_page': page,
            'total_pages': total_pages,
            'has_previous': page > 1,
            'has_next': page < total_pages,
            'previous_page': page - 1,
            'next_page': page + 1,
            'page_range': range(max(1, page - 2), min(total_pages + 1, page + 3)),
        }
        
    except Exception as e:
        logger.error(f"Error in media library view: {str(e)}", exc_info=True)
        user_images = []
        pagination = None
        messages.error(request, f"Error loading images: {str(e)}")

    # Handle file upload (POST request)
    if request.method == 'POST':

        if 'image_name' in request.POST:
            # Handle image name update
            try:
                image_id = request.POST.get('image_id')
                if not image_id:
                    raise ValueError("Image ID is required")
                
                image_id = int(image_id)  # Convert to integer explicitly
                new_name = request.POST.get('image_name').strip()
                
                if not new_name:
                    raise ValueError("Image name cannot be empty")

                image = MenuImage.objects.get(id=image_id, user=request.user)
                image.name = new_name
                image.save()
                messages.success(request, 'Image name updated successfully.')
            
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid image ID or name: {str(e)}")
                messages.error(request, 'Invalid image ID or name provided.')
            except MenuImage.DoesNotExist:
                messages.error(request, 'Image not found.')

        uploaded_file = request.FILES.get('image')
        if uploaded_file:
            try:
                upload_result = cloudinary.uploader.upload(
                    uploaded_file,
                    folder=f"media_library/user_{request.user.id}",
                    tags=[f"user_{request.user.id}", "media_library"],
                    context={"user_id": str(request.user.id)},
                )
                
                menu_image = MenuImage.objects.create(
                    user=request.user,
                    image=upload_result['public_id'],
                    public_id=upload_result['public_id'],
                    image_type='general'
                )
                
                messages.success(request, "Image uploaded successfully!")
                
            except Exception as e:
                logger.error(f"Upload error: {str(e)}", exc_info=True)
                messages.error(request, f"Upload failed: {str(e)}")
        return redirect('media_library')

    return render(request, 'myapp/media_library.html', {
        'images': user_images,
        'pagination': pagination,
    })

@login_required
def delete_image(request, public_id):
    if request.method == 'POST':
        try:
            logger.debug(f"Attempting to delete image: {public_id}")
            
            # Verify the image belongs to the user
            menu_image = MenuImage.objects.filter(
                user=request.user,
                public_id=public_id
            ).first()

            if menu_image:
                # Delete from Cloudinary
                cloudinary.api.delete_resources([public_id])
                
                # Delete from database
                menu_image.delete()
                
                messages.success(request, "Image deleted successfully")
            else:
                messages.error(request, "Image not found or access denied")
                logger.warning(f"Attempted to delete unauthorized image: {public_id} by user {request.user.id}")
                
        except Exception as e:
            logger.error(f"Error deleting image {public_id}: {str(e)}")
            messages.error(request, f"Error deleting image: {str(e)}")
    else:
        messages.error(request, "Invalid request method")
    
    return redirect('media_library')

@login_required
def apply_transformation(request, public_id):
    if request.method == 'POST':
        transformation = request.POST.get('transformation')
        if not transformation:
            messages.error(request, "No transformation selected.")
            return redirect('media_library')

        try:
            # Apply the transformation and overwrite the image
            result = cloudinary.uploader.explicit(
                public_id,
                type="upload",
                eager=[{"transformation": transformation}],
                overwrite=True  # Ensure original image is replaced
            )

            # Log the result for debugging
            print(f"Cloudinary response: {result}")

            messages.success(request, "Transformation applied successfully.")
        except Exception as e:
            messages.error(request, f"Error applying transformation: {str(e)}")

        return redirect('media_library')

    messages.error(request, "Invalid request method.")
    return redirect('media_library')


@login_required
def delete_menu_image(request, image_id):
    try:
        # Fetch the image associated with the menu
        image = MenuImage.objects.get(id=image_id, user=request.user)
        image.delete()  # Remove the image record from the database

        # Optionally delete the image from Cloudinary
        if image.image:
            cloudinary.api.delete_resources([image.image.public_id])

        messages.success(request, "Menu image deleted successfully.")
    except MenuImage.DoesNotExist:
        messages.error(request, "Menu image not found.")
    except Exception as e:
        messages.error(request, f"Error deleting menu image: {str(e)}")
    return redirect('scan_page')  # Corrected to match the name in urls.py

@login_required
def batch_delete_images(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            public_ids = data.get('public_ids', [])

            if not public_ids:
                return JsonResponse({'success': False, 'error': 'No images selected'})

            # Verify all images belong to the user
            user_images = MenuImage.objects.filter(
                user=request.user,
                public_id__in=public_ids
            )

            if len(user_images) != len(public_ids):
                return JsonResponse({'success': False, 'error': 'Unauthorized access to some images'})

            # Delete from Cloudinary
            cloudinary.api.delete_resources(public_ids)
            
            # Delete from database
            user_images.delete()

            return JsonResponse({
                'success': True,
                'message': f'Successfully deleted {len(public_ids)} images'
            })

        except Exception as e:
            logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': str(e)
            })

    return JsonResponse({'success': False, 'error': 'Invalid request method'})

# views.py - Add new view
@login_required
def batch_delete_items(request):
    if request.method == 'POST':
        try:
            item_ids = json.loads(request.POST.get('item_ids', '[]'))
            # Verify all items belong to the user
            items = MenuItem.objects.filter(
                id__in=item_ids,
                menu__user=request.user
            )
            deleted_count = items.delete()[0]
            messages.success(request, f'Successfully deleted {deleted_count} items')
            return JsonResponse({
                'status': 'success',
                'message': f'Successfully deleted {deleted_count} items'
            })
        except Exception as e:
            messages.error(request, f'Error deleting items: {str(e)}')
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

# views.py - Add these new views

@login_required
def publish_dashboard(request):
    # Add some debug prints
    templates = Template.objects.all()
    print("=== Templates in Database ===")
    for template in templates:
        print(f"ID: {template.id}, Name: {template.name}")
    
    published_menus = PublishedMenu.objects.filter(user=request.user)

    context = {
        'templates': templates,
        'published_menus': published_menus,
        'subscription_level': request.user.subscription.level
    }
    return render(request, 'myapp/publish/dashboard.html', context)

@login_required
def template_preview(request, template_id):
    template = get_object_or_404(Template, id=template_id)
    menu = None
    default_name = "Sample Menu"  # Default name when no menu is selected
    
    if request.method == 'POST':
        menu_id = request.POST.get('menu_id')
        if menu_id:
            menu = get_object_or_404(
                Menu.objects.select_related('user').prefetch_related(
                    'categories',
                    'categories__menuitem_set',
                    'categories__images',
                    'categories__menuitem_set__images'
                ), 
                id=menu_id, 
                user=request.user
            )
    
    subscription_level = request.user.subscription.level
    show_customization = subscription_level in ['basic', 'premium']

    # Create a mock published menu for the preview
    mock_published_menu = type('MockPublishedMenu', (), {
        'custom_css': '',
        'custom_colors': {},
        'custom_fonts': {},
        'user': request.user
    })
    
    context = {
        'template': template,
        'menu': menu,
        'default_name': default_name,  # Add default name to context
        'available_menus': Menu.objects.filter(user=request.user),
        'show_customization': show_customization,
        'subscription_level': subscription_level,
        'published_menu': mock_published_menu,
        'colors': {'primary': '#000000', 'secondary': '#666666', 'background': '#ffffff'},
        'fonts': {'heading': 'Arial', 'body': 'Arial'},
        'user': request.user
    }
    
    return render(request, 'myapp/publish/preview.html', context)

@login_required
def publish_menu(request, template_id):
    template = get_object_or_404(Template, id=template_id)
    
    # Get customizations from URL if present
    initial_customizations = {}
    if request.GET.get('customizations'):
        try:
            initial_customizations = json.loads(request.GET.get('customizations'))
            print("Received customizations from URL:", initial_customizations)
        except json.JSONDecodeError:
            print("Failed to parse customizations from URL")
    
    if request.method == 'POST':
        print("POST data received:", request.POST)
        form = PublishMenuForm(request.POST, user=request.user)
        if form.is_valid():
            menu = form.cleaned_data['menu']
            overwrite = form.cleaned_data.get('overwrite_existing', False)
            new_slug = form.cleaned_data.get('slug')

            # Get customizations from the POST data
            customizations = {
                'colors': {
                    'primary': request.POST.get('primary_color'),
                    'secondary': request.POST.get('secondary_color'),
                    'background': request.POST.get('background_color')
                },
                'fonts': {
                    'heading': request.POST.get('heading_font'),
                    'body': request.POST.get('body_font')
                },
                'custom_css': request.POST.get('custom_css', '')
            }

            print("Processing customizations:", customizations)

            try:
                published_menu = PublishedMenu.objects.filter(user=request.user, menu=menu).first()
                
                if published_menu and overwrite:
                    published_menu.template = template
                    published_menu.custom_colors = customizations['colors']
                    published_menu.custom_fonts = customizations['fonts']
                    published_menu.custom_css = customizations['custom_css']
                    if new_slug:
                        published_menu.slug = new_slug
                    published_menu.status = 'published'
                    published_menu.published_at = timezone.now()
                    published_menu.save()
                    
                    print(f"Updated menu with customizations: {published_menu.custom_colors}")
                    messages.success(request, "Menu updated and published successfully!")
                else:
                    published_menu = PublishedMenu.objects.create(
                        user=request.user,
                        menu=menu,
                        template=template,
                        custom_colors=customizations['colors'],
                        custom_fonts=customizations['fonts'],
                        custom_css=customizations['custom_css'],
                        slug=new_slug,
                        status='published',
                        published_at=timezone.now()
                    )
                    print(f"Created new menu with customizations: {published_menu.custom_colors}")
                    messages.success(request, "Menu published successfully!")

                return redirect('publish_dashboard')
                
            except Exception as e:
                print(f"Publishing error: {str(e)}")
                messages.error(request, f"Error publishing menu: {str(e)}")
    else:
        initial_menu = request.GET.get('menu_id')
        form = PublishMenuForm(user=request.user, initial={'menu': initial_menu})

    context = {
        'form': form,
        'template': template,
        'initial_customizations': initial_customizations
    }
    return render(request, 'myapp/publish/publish_form.html', context)

@login_required
def customize_template(request, published_menu_id):
    published_menu = get_object_or_404(PublishedMenu, id=published_menu_id, user=request.user)
    
    templates = Template.objects.all()
    # Debugging templates
    print("=== Templates in Database ===")
    for template in templates:
        print(f"ID: {template.id}, Name: {template.name}")
    
    if not templates.exists():
        print("No templates found!")

    if request.method == 'POST':
        form = TemplateCustomizationForm(request.POST, instance=published_menu)
        if form.is_valid():
            try:
                # Validate JSONFields if needed
                custom_colors = form.cleaned_data.get('custom_colors')
                custom_fonts = form.cleaned_data.get('custom_fonts')

                # Convert JSON strings back to Python dicts if necessary
                if isinstance(custom_colors, str):
                    import json
                    custom_colors = json.loads(custom_colors)
                if isinstance(custom_fonts, str):
                    custom_fonts = json.loads(custom_fonts)

                # Save the instance with validated data
                published_menu.custom_colors = custom_colors
                published_menu.custom_fonts = custom_fonts
                published_menu.save()
                messages.success(request, "Customizations saved successfully!")
            except Exception as e:
                messages.error(request, f"Error saving customizations: {e}")
        else:
            messages.error(request, "Please correct the errors in the form.")
    else:
        form = TemplateCustomizationForm(instance=published_menu)

    return render(request, 'myapp/publish/customize.html', {
        'form': form,
        'published_menu': published_menu,
        'templates': templates,  # Pass templates for selection or debugging
    })




@login_required
def domain_settings(request, published_menu_id):
    published_menu = get_object_or_404(PublishedMenu, id=published_menu_id, user=request.user)
    
    if request.method == 'POST':
        form = DomainSettingsForm(request.POST, instance=published_menu)
        if form.is_valid():
            form.save()
            messages.success(request, "Domain settings updated!")
            return redirect('publish_dashboard')
    else:
        form = DomainSettingsForm(instance=published_menu)
    
    context = {
        'form': form,
        'published_menu': published_menu
    }
    return render(request, 'myapp/publish/domain_settings.html', context)

@login_required
def template_analytics(request, published_menu_id):
    published_menu = get_object_or_404(PublishedMenu, id=published_menu_id, user=request.user)
    analytics = TemplateAnalytics.objects.filter(published_menu=published_menu)
    
    context = {
        'published_menu': published_menu,
        'analytics': analytics
    }
    return render(request, 'myapp/publish/analytics.html', context)

def view_published_menu(request, slug):
    """Public view for accessing published menus"""
    published_menu = get_object_or_404(PublishedMenu, 
                                     slug=slug,
                                     status='published')
    
    # Update view count and last viewed timestamp
    published_menu.view_count += 1
    published_menu.last_viewed_at = timezone.now()
    published_menu.save()
    
    # Update or create analytics for today
    today = timezone.now().date()
    analytics, created = TemplateAnalytics.objects.get_or_create(
        published_menu=published_menu,
        date=today,
        defaults={
            'view_count': 1,
            'unique_visitors': 1
        }
    )
    
    if not created:
        # Update existing analytics
        analytics.view_count += 1
        analytics.save()
    
    # Get all menu items organized by category
    categories = published_menu.menu.categories.prefetch_related('menuitem_set', 'images').all()
    
    # Get the template
    template = published_menu.template
    
    # Get template content from MenuTemplate
    menu_template = MenuTemplate.objects.filter(name=template.name).first()
    if not menu_template:
        # Fallback to empty strings if template not found
        css_content = ''
        js_content = ''
    else:
        css_content = menu_template.css_content
        js_content = menu_template.js_content

    context = {
        'menu': published_menu.menu,
        'categories': categories,
        'published_menu': published_menu,
        'template': template,
        # Add template-specific content
        'css_template': css_content,
        'js_template': js_content,
        # Customizations
        'colors': published_menu.custom_colors or {},
        'fonts': published_menu.custom_fonts or {},
        'custom_css': published_menu.custom_css or '',
    }

    # Log the context for debugging
    print("Template CSS:", css_content)
    print("Colors:", published_menu.custom_colors)
    print("Fonts:", published_menu.custom_fonts)

    return render(request, 'myapp/published_menu.html', context)


@login_required
def unpublish_menu(request, published_menu_id):
    published_menu = get_object_or_404(PublishedMenu, id=published_menu_id, user=request.user)
    if request.method == 'POST':
        published_menu.unpublish()
        messages.success(request, "Menu has been unpublished successfully.")
        return redirect('publish_dashboard')
    return redirect('publish_dashboard')

@login_required
def delete_published_menu(request, published_menu_id):
    published_menu = get_object_or_404(PublishedMenu, id=published_menu_id, user=request.user)
    if request.method == 'POST':
        published_menu.delete()
        messages.success(request, "Published menu has been deleted successfully.")
        return redirect('publish_dashboard')
    return redirect('publish_dashboard')

@login_required
def republish_menu(request, published_menu_id):
    published_menu = get_object_or_404(PublishedMenu, id=published_menu_id, user=request.user)
    if request.method == 'POST':
        # Get the new slug from the form
        new_slug = request.POST.get('new_slug')
        if new_slug:
            # Check if slug is available
            if PublishedMenu.objects.filter(slug=new_slug).exclude(id=published_menu_id).exists():
                messages.error(request, "This URL is already in use. Please choose another.")
                return redirect('publish_dashboard')
            
            published_menu.slug = new_slug
            
        published_menu.status = 'published'
        published_menu.published_at = timezone.now()
        published_menu.save()
        
        messages.success(request, "Menu has been republished successfully.")
        return redirect('publish_dashboard')
    return redirect('publish_dashboard')

@login_required
def update_menu_order(request):
    if request.method == 'POST':
        try:
            # Add debugging
            print("Received request body:", request.body)
            
            data = json.loads(request.body)
            category_id = data.get('category_id')
            items = data.get('items', [])

            if not category_id or not items:
                return JsonResponse({
                    'success': False, 
                    'error': 'Missing required data'
                }, status=400)

            try:
                category = MenuCategory.objects.get(
                    id=category_id, 
                    menu__user=request.user
                )
            except MenuCategory.DoesNotExist:
                return JsonResponse({
                    'success': False, 
                    'error': 'Category not found'
                }, status=404)

            # Update the order of each item
            for position, item_data in enumerate(items):
                MenuItem.objects.filter(
                    id=item_data['id'],
                    category=category
                ).update(order=position)

            return JsonResponse({'success': True})
            
        except json.JSONDecodeError as e:
            return JsonResponse({
                'success': False, 
                'error': f'Invalid JSON: {str(e)}'
            }, status=400)
        except Exception as e:
            print(f"Error in update_menu_order: {str(e)}")
            return JsonResponse({
                'success': False, 
                'error': str(e)
            }, status=400)
    
    return JsonResponse({
        'success': False, 
        'error': 'Invalid request method'
    }, status=405)


@login_required
def update_category_order(request):
    if request.method == 'POST':
        try:
            # Log the raw request body
            logger.debug(f"Received request body: {request.body}")
            
            data = json.loads(request.body)
            categories = data.get('categories', [])

            logger.debug(f"Parsed categories data: {categories}")

            if not categories:
                logger.warning("No categories data provided")
                return JsonResponse({
                    'success': False,
                    'error': 'No category data provided'
                }, status=400)

            # Log the user and categories being updated
            logger.debug(f"User {request.user.id} attempting to update categories: {categories}")
            
            with transaction.atomic():
                for category_data in categories:
                    category_id = category_data.get('id')
                    new_order = category_data.get('order')
                    
                    # Verify the category exists and belongs to the user
                    category = MenuCategory.objects.filter(
                        id=category_id,
                        menu__user=request.user
                    ).first()
                    
                    if category:
                        category.order = new_order
                        category.save()
                        logger.debug(f"Updated category {category_id} to order {new_order}")
                    else:
                        logger.warning(f"Category {category_id} not found or doesn't belong to user")

            return JsonResponse({'success': True})

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f'Invalid JSON data: {str(e)}'
            }, status=400)
        except Exception as e:
            logger.error(f"Error updating category order: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)

    return JsonResponse({
        'success': False,
        'error': 'Invalid request method'
    }, status=405)

@login_required
def update_image_name(request, image_id):
    if request.method == 'POST':
        try:
            image = MenuImage.objects.get(id=image_id, user=request.user)
            data = json.loads(request.body)
            image.name = data.get('name')
            image.save()
            return JsonResponse({'success': True, 'name': image.name})
        except MenuImage.DoesNotExist:
            return
        

@login_required
def edit_image_name(request, image_id):
    if request.method == 'POST':
        try:
            image = MenuImage.objects.get(id=image_id, user=request.user)
            new_name = request.POST.get('new_name', '').strip()
            if new_name:
                image.name = new_name
                image.save()
                messages.success(request, "Image name updated successfully.")
            else:
                messages.error(request, "Please provide a valid name.")
        except MenuImage.DoesNotExist:
            messages.error(request, "Image not found.")
    return redirect('scan_page')


@login_required
def preview_menu(request, published_menu_id):
    published_menu = get_object_or_404(PublishedMenu, id=published_menu_id, user=request.user)

    try:
        # Dynamically get the file paths
        html_file_path = published_menu.template.get_html_file()
        css_file_path = published_menu.template.get_css_file()

        # Include the CSS file path in the context
        context = {
            'menu': published_menu.menu,
            'published_menu': published_menu,
            'colors': published_menu.custom_colors,
            'fonts': published_menu.custom_fonts,
            'custom_css': published_menu.custom_css,
            'css_file_path': css_file_path,  # Add CSS path
        }

        # Render the HTML template dynamically
        preview_html = render_to_string(html_file_path, context)

        return JsonResponse({'preview_html': preview_html})

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in preview_menu view: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def transform_image(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            public_id = data.get('public_id')
            transformation = data.get('transformation')

            # Get the image
            image = get_object_or_404(MenuImage, public_id=public_id, user=request.user)
            
            try:
                if transformation == 'remove_background':
                    # Use the background removal API
                    result = cloudinary.uploader.upload(
                        image.get_cloudinary_url(),
                        public_id=public_id,  # Keep the same public_id
                        background_removal="cloudinary_ai",
                        resource_type="image",
                        overwrite=True,  # Ensure we overwrite the existing image
                        invalidate=True   # Invalidate CDN cache
                    )
                else:
                    # For auto_rotate and auto_color, use transformation URL
                    transformation_params = {
                        'auto_rotate': [{"angle": "auto"}],
                        'auto_color': [{"effect": "auto_color"}]
                    }
                    
                    result = cloudinary.uploader.explicit(
                        public_id,
                        type="upload",
                        transformation=transformation_params.get(transformation, []),
                        resource_type="image",
                        invalidate=True
                    )

                # Get both URLs for verification
                transformed_url = result.get('secure_url')
                original_url = image.get_cloudinary_url()

                if not transformed_url:
                    raise Exception("No URL returned from Cloudinary")

                # Log the URLs for debugging
                logger.debug(f"Original URL: {original_url}")
                logger.debug(f"Transformed URL: {transformed_url}")

                return JsonResponse({
                    'success': True,
                    'url': transformed_url,
                    'public_id': public_id
                })

            except Exception as cloudinary_error:
                logger.error(f"Cloudinary transformation error: {str(cloudinary_error)}")
                return JsonResponse({
                    'success': False,
                    'error': f"Cloudinary error: {str(cloudinary_error)}"
                })

        except Exception as e:
            logger.error(f"General transformation error: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            })

    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def save_image_changes(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            public_id = data.get('public_id')
            image_data = data.get('image_data')
            
            # Remove the data URL prefix to get just the base64 image data
            image_data = image_data.split(',')[1]
            
            # Upload the modified image to Cloudinary
            result = cloudinary.uploader.upload(
                f"data:image/png;base64,{image_data}",
                public_id=public_id,
                overwrite=True,
                invalidate=True
            )

            return JsonResponse({'success': True})

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })

    return JsonResponse({'success': False, 'error': 'Invalid request method'})



@login_required
def select_template_and_menu(request):
    if request.method == 'POST':
        template_id = request.POST.get('template_id')
        menu_id = request.POST.get('menu_id')

        # Ensure both IDs are valid
        template = get_object_or_404(Template, id=template_id)
        menu = get_object_or_404(Menu, id=menu_id, user=request.user)

        # Redirect to the customize_template view with selected IDs
        return redirect('customize_template', published_menu_id=menu.id)

    # Provide available templates and menus for selection
    templates = Template.objects.all()
    menus = Menu.objects.filter(user=request.user)

    return render(request, 'myapp/select_template_and_menu.html', {
        'templates': templates,
        'menus': menus,
    })


