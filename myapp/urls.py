# myapp/urls.py
from django.urls import path
from . import views
from . import api_views
from .views import preview_menu

urlpatterns = [

    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('features/', views.features, name='features'),
    path('pricing/', views.pricing, name='pricing'),
    path('contact/', views.contact, name='contact'),

    # Auth URLs
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Main app URLs
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('scan/', views.scan_view, name='scan_page'),
    path('upload-image/', views.upload_image, name='upload_image'),
    path('process-image/', views.process_image, name='process_image'),
    path('update-menu-order/', views.update_menu_order, name='update_menu_order'),

    # Menu management URLs
    path('menus/<int:menu_id>/', views.all_menus,
         name='all_menus'),  # This one first
    path('menus/', views.all_menus, name='all_menus'),
    path('item/edit/<int:item_id>/', views.edit_item, name='edit_item'),
    path('item/delete/<int:item_id>/', views.delete_item, name='delete_item'),
    path('menus/<int:menu_id>/category/add/',
         views.add_category, name='add_category_to_menu'),
    path('menus/<int:menu_id>/item/add/',
         views.add_item, name='add_item_to_menu'),
    path('categories/<int:category_id>/delete/',
         views.delete_category, name='delete_category'),
    path('categories/<int:category_id>/edit/',
         views.edit_category, name='edit_category'),
    path('items/<int:item_id>/edit/', views.edit_item, name='edit_item'),
    path('menus/<int:menu_id>/rename/', views.rename_menu, name='rename_menu'),
    path('menus/<int:menu_id>/delete/', views.delete_menu, name='delete_menu'),
    path('media-library/', views.media_library, name='media_library'),
    path('media-library/delete/<path:public_id>/',
         views.delete_image, name='delete_image'),
    path('media-library/transform/<str:public_id>/',
         views.apply_transformation, name='apply_transformation'),
    path('menus/images/<int:image_id>/delete/',
         views.delete_menu_image, name='delete_menu_image'),
    path('media-library/batch-delete/',
         views.batch_delete_images, name='batch_delete_images'),
    path('items/batch-delete/', views.batch_delete_items,
         name='batch_delete_items'),
    path('publish/', views.publish_dashboard, name='publish_dashboard'),
    path('publish/template/<int:template_id>/preview/',
         views.template_preview, name='template_preview'),
    path('publish/template/<int:template_id>/use/',
         views.publish_menu, name='publish_menu'),
    path('publish/menu/<int:published_menu_id>/customize/',
         views.customize_template, name='customize_template'),
    path('publish/menu/<int:published_menu_id>/domain/',
         views.domain_settings, name='domain_settings'),
    path('publish/menu/<int:published_menu_id>/analytics/',
         views.template_analytics, name='template_analytics'),
    path('publish/menu/<int:published_menu_id>/unpublish/',
         views.unpublish_menu, name='unpublish_menu'),
    path('publish/menu/<int:published_menu_id>/delete/',
         views.delete_published_menu, name='delete_published_menu'),
    path('publish/menu/<int:published_menu_id>/republish/',
         views.republish_menu, name='republish_menu'),
    # Add this before any catch-all patterns
    path('m/<str:slug>', views.view_published_menu, name='view_published_menu'),
    path('update-menu-order/', views.update_menu_order, name='update_menu_order'),
    path('update-category-order/', views.update_category_order,
         name='update_category_order'),
    path('media-library/update-name/<int:image_id>/',
         views.update_image_name, name='update_image_name'),
         path('menus/images/<int:image_id>/edit-name/', views.edit_image_name, name='edit_image_name'),
     path('preview/menu/<int:published_menu_id>/', preview_menu, name='preview_menu'),
     path('publish/select-template-and-menu/', views.select_template_and_menu, name='select_template_and_menu'),
     path('media-library/transform/', views.transform_image, name='transform_image'),
     path('media-library/save-changes/', views.save_image_changes, name='save_image_changes'),
     path('verify-password/', views.verify_password, name='verify_password'),

]
