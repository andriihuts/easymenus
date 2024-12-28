from myapp.models import Menu, MenuCategory, MenuItem, MenuImage
import logging

logger = logging.getLogger(__name__)

def populate_menu_from_json(menu, menu_data, action='new'):
    """
    Given a Menu instance and the menu_data (dict) from GPT,
    create/update MenuCategory and MenuItem models.
    action can be 'new', 'existing', or 'add'
    """
    try:
        # Only clear existing categories if we're not adding to the menu
        if action != 'add':
            MenuCategory.objects.filter(menu=menu).delete()

        # Store the raw menu_data in the Menu model
        if action == 'add':
            # Merge the new menu_data with existing data
            existing_data = menu.menu_data or {"menu_categories": []}
            existing_categories = existing_data.get("menu_categories", [])
            new_categories = menu_data.get("menu_categories", [])
            menu.menu_data = {
                "menu_categories": existing_categories + new_categories
            }
        else:
            menu.menu_data = menu_data
        menu.save()

        # Loop over categories
        for cat_data in menu_data.get("menu_categories", []):
            try:
                # For 'add' action, check if category exists
                if action == 'add':
                    category = MenuCategory.objects.filter(
                        menu=menu,
                        name=cat_data.get("category_name")
                    ).first()
                    
                    if category:
                        logger.info(f"Adding items to existing category: {category.name}")
                    else:
                        category = MenuCategory.objects.create(
                            menu=menu,
                            name=cat_data.get("category_name"),
                            name_secondary=cat_data.get("category_name_secondary", "")
                        )
                        logger.info(f"Created new category: {category.name}")
                else:
                    category = MenuCategory.objects.create(
                        menu=menu,
                        name=cat_data.get("category_name"),
                        name_secondary=cat_data.get("category_name_secondary", "")
                    )

                # Create menu items
                for item_data in cat_data.get("menu_items", []):
                    try:
                        # Check for duplicate items when adding
                        if action == 'add':
                            existing_item = MenuItem.objects.filter(
                                menu=menu,
                                category=category,
                                title=item_data.get("title", "")
                            ).first()
                            
                            if existing_item:
                                logger.info(f"Skipping duplicate item: {existing_item.title}")
                                continue

                        # Create the menu item
                        menu_item = MenuItem.objects.create(
                            menu=menu,
                            category=category,
                            title=item_data.get("title", ""),
                            description=item_data.get("description", ""),
                            cost=item_data.get("cost", 0.0),
                            options=item_data.get("options", [])
                        )

                        # Associate matched image if available
                        if matched_image_id := item_data.get("matched_image_id"):
                            try:
                                menu_image = MenuImage.objects.get(
                                    public_id=matched_image_id,
                                    user=menu.user
                                )
                                menu_item.images.add(menu_image)
                                logger.info(f"Associated image {matched_image_id} with menu item {menu_item.id}")
                            except MenuImage.DoesNotExist:
                                logger.warning(
                                    f"Matched image {matched_image_id} not found for menu item {menu_item.id}"
                                )
                            except Exception as e:
                                logger.error(f"Error associating image with menu item: {str(e)}")

                    except Exception as item_error:
                        logger.error(f"Error creating menu item: {str(item_error)}")
                        continue

            except Exception as cat_error:
                logger.error(f"Error creating category: {str(cat_error)}")
                continue

        return menu

    except Exception as e:
        logger.error(f"Error in populate_menu_from_json: {str(e)}")
        raise