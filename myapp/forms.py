import cloudinary
import cloudinary.uploader
import cloudinary.api
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import (
    User, 
    Subscription, 
    MenuCategory, 
    MenuItem,
    Menu, 
    MenuImage,
    PublishedMenu,
)
from django import forms
from django.forms.widgets import Textarea, HiddenInput

# User Related Forms
class SignUpForm(UserCreationForm):
    name = forms.CharField(required=True)
    business_name = forms.CharField(required=True)

    class Meta:
        model = User
        fields = ['email', 'name', 'business_name', 'password1', 'password2']

class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        widget=forms.EmailInput(attrs={'autofocus': True}), 
        label="Email"
    )

class BusinessProfileUpdateForm(forms.ModelForm):
    business_location = forms.CharField(
        required=False,
        widget=forms.Textarea,
        help_text="Enter JSON data for location. E.g. {\"city\": \"New York\", \"country\": \"USA\"}"
    )

    class Meta:
        model = User
        fields = ['business_name', 'business_description', 'business_location']

    def clean_business_location(self):
        data = self.cleaned_data.get('business_location', '{}').strip()
        if not data:
            return {}
        import json
        try:
            location_json = json.loads(data)
        except json.JSONDecodeError:
            raise forms.ValidationError("Invalid JSON for business location.")
        return location_json

# Subscription Related Forms
class SubscriptionUpdateForm(forms.ModelForm):
    class Meta:
        model = Subscription
        fields = ['level', 'billing_cycle']

# Menu Related Forms
class MenuCreationForm(forms.ModelForm):
    class Meta:
        model = Menu
        fields = ['name']

class CategoryForm(forms.ModelForm):
    media_library = forms.MultipleChoiceField(
        choices=[],
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Media Library Images"
    )

    class Meta:
        model = MenuCategory
        fields = ['name', 'name_secondary', 'order']

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['order'].required = False

        if self.user:
            try:
                # Get user's images from MenuImage model
                user_images = MenuImage.objects.filter(
                    user=self.user,
                    image_type='general'
                )
                
                # Create choices from user's images
                self.fields['media_library'].choices = [
                    (image.public_id, image.public_id) 
                    for image in user_images
                ]
                
                # If this is an existing category, pre-select its images
                if self.instance.pk:
                    self.initial['media_library'] = [
                        image.public_id for image in self.instance.images.all()
                    ]
                    
            except Exception as e:
                logger.error(f"Error setting up media library choices: {str(e)}")
                self.fields['media_library'].choices = []

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        if commit:
            instance.save()
            
            # Handle the media library images
            if 'media_library' in self.cleaned_data:
                selected_image_ids = self.cleaned_data['media_library']
                instance.images.clear()
                
                for public_id in selected_image_ids:
                    menu_image, created = MenuImage.objects.get_or_create(
                        user=self.user,
                        public_id=public_id,
                        defaults={
                            'image': public_id,
                        }
                    )
                    instance.images.add(menu_image)

        return instance

class MenuItemForm(forms.ModelForm):
    media_library = forms.MultipleChoiceField(
        choices=[],  # We'll set these dynamically
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Media Library Images"
    )

    class Meta:
        model = MenuItem
        fields = [
            'title',
            'title_secondary',
            'description',
            'description_secondary',
            'cost',
            'category',
        ]

    def __init__(self, *args, **kwargs):
        self.menu = kwargs.pop('menu', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if self.menu:
            self.fields['category'].queryset = MenuCategory.objects.filter(menu=self.menu)

        if self.user:
            try:
                # Get user's images from MenuImage model
                user_images = MenuImage.objects.filter(
                    user=self.user,
                    image_type='general'
                )
                
                # Create choices from user's images
                self.fields['media_library'].choices = [
                    (image.public_id, image.public_id) 
                    for image in user_images
                ]
                
                # If this is an existing item, pre-select its images
                if self.instance.pk:
                    self.initial['media_library'] = [
                        image.public_id for image in self.instance.images.all()
                    ]
                    
            except Exception as e:
                logger.error(f"Error setting up media library choices: {str(e)}")
                self.fields['media_library'].choices = []


# Image Upload Forms
class MenuImageUploadForm(forms.Form):
    image = forms.ImageField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*'
        })
    )


# Menu Processing Forms
class MenuProcessingForm(forms.Form):
    CHOICES = [
        ('new', 'Create New Menu'),
        ('existing', 'Update Existing Menu')
    ]
    action = forms.ChoiceField(choices=CHOICES, widget=forms.RadioSelect)
    menu_name = forms.CharField(required=False)
    existing_menu = forms.ModelChoiceField(queryset=None, required=False)

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['existing_menu'].queryset = Menu.objects.filter(user=user)

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        menu_name = cleaned_data.get('menu_name')
        existing_menu = cleaned_data.get('existing_menu')

        if action == 'new' and not menu_name:
            raise forms.ValidationError("Menu name is required when creating a new menu")
        elif action == 'existing' and not existing_menu:
            raise forms.ValidationError("Please select an existing menu")

        return cleaned_data
    
# forms.py - Update BusinessProfileUpdateForm
class BusinessProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            # Business Information
            'business_name',
            'business_description',
            
            # Address
            'address_line1',
            'address_line2',
            'city',
            'state_province',
            'postal_code',
            'country',
            
            # Online Presence
            'website_url',
            'facebook_url',
            'instagram_username',
            'twitter_username',
            'bluesky_handle',
            'threads_username',
        ]
        
        labels = {
            # Business Information
            'business_name': 'Business Name',
            'business_description': 'Business Description',
            
            # Address
            'address_line1': 'Street Address',
            'address_line2': 'Apt, Suite, Unit, etc.',
            'city': 'City',
            'state_province': 'State/Province',
            'postal_code': 'ZIP/Postal Code',
            'country': 'Country',
            
            # Online Presence
            'website_url': 'Website URL',
            'facebook_url': 'Facebook Page URL',
            'instagram_username': 'Instagram Username',
            'twitter_username': 'Twitter Username',
            'bluesky_handle': 'Bluesky Handle',
            'threads_username': 'Threads Username',
        }
        
        widgets = {
            'business_description': forms.Textarea(attrs={'rows': 4}),
            'address_line1': forms.TextInput(attrs={'placeholder': 'Street address'}),
            'address_line2': forms.TextInput(attrs={'placeholder': 'Apartment, suite, unit, etc.'}),
            'instagram_username': forms.TextInput(attrs={'placeholder': '@username'}),
            'twitter_username': forms.TextInput(attrs={'placeholder': '@username'}),
            'bluesky_handle': forms.TextInput(attrs={'placeholder': '@handle.bsky.social'}),
            'threads_username': forms.TextInput(attrs={'placeholder': '@username'}),
        }

class PublishMenuForm(forms.ModelForm):
    overwrite_existing = forms.BooleanField(required=False, initial=False,
        label="Overwrite existing published menu",
        help_text="Check this to update your existing published menu with these settings")

    class Meta:
        model = PublishedMenu
        fields = ['menu', 'slug', 'overwrite_existing']

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user:
            self.fields['menu'].queryset = Menu.objects.filter(user=user)
            # Check if menu is already published
            if 'menu' in self.initial:
                try:
                    existing = PublishedMenu.objects.get(
                        user=user,
                        menu_id=self.initial['menu']
                    )
                    self.fields['overwrite_existing'].initial = True
                    self.fields['slug'].initial = existing.slug
                except PublishedMenu.DoesNotExist:
                    pass

    def clean(self):
        cleaned_data = super().clean()
        menu = cleaned_data.get('menu')
        slug = cleaned_data.get('slug')

        if menu and self.user:
            try:
                existing = PublishedMenu.objects.get(user=self.user, menu=menu)
                if not cleaned_data.get('overwrite_existing'):
                    raise forms.ValidationError(
                        "This menu is already published. Check 'Overwrite existing' to update it."
                    )
                # Check if new slug is unique (excluding current menu)
                if slug and slug != existing.slug:
                    if PublishedMenu.objects.filter(slug=slug).exclude(id=existing.id).exists():
                        raise forms.ValidationError("This URL is already in use.")
            except PublishedMenu.DoesNotExist:
                # Check if new slug is unique
                if slug and PublishedMenu.objects.filter(slug=slug).exists():
                    raise forms.ValidationError("This URL is already in use.")

        return cleaned_data

class TemplateCustomizationForm(forms.ModelForm):
    class Meta:
        model = PublishedMenu
        fields = ['custom_css', 'custom_colors', 'custom_fonts']
        widgets = {
            'custom_css': forms.Textarea(attrs={
                'class': 'font-mono',
                'rows': 10,
                'placeholder': '/* Add your custom CSS here */'
            }),
            'custom_colors': forms.JSONField(),
            'custom_fonts': forms.JSONField(),
        }

    def clean_custom_css(self):
        css = self.cleaned_data.get('custom_css')
        if css and not self.instance.user.subscription.level == 'premium':
            raise forms.ValidationError("Custom CSS is only available for premium users.")
        return css

class DomainSettingsForm(forms.ModelForm):
    class Meta:
        model = PublishedMenu
        fields = ['custom_domain']
        
    def clean_custom_domain(self):
        domain = self.cleaned_data.get('custom_domain')
        if domain and not self.instance.user.subscription.level == 'premium':
            raise forms.ValidationError("Custom domains are only available for premium users.")
        return domain