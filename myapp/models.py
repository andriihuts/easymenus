from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.base_user import BaseUserManager
from django.conf import settings
from django.utils import timezone
from cloudinary.models import CloudinaryField
import uuid
import re
from django.utils.text import slugify

class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Users must have an email address')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)

# models.py - Update User model with new fields
class User(AbstractUser):
    username = None
    active_menu = models.ForeignKey('Menu', on_delete=models.SET_NULL, null=True, blank=True, related_name='active_users')
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    
    # Business Information
    business_name = models.CharField(max_length=255, blank=True, null=True)
    business_description = models.TextField(blank=True, null=True)
    business_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    
    # Address Fields
    address_line1 = models.CharField(max_length=255, blank=True, null=True)
    address_line2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state_province = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    
    # Online Presence
    website_url = models.URLField(max_length=255, blank=True, null=True)
    facebook_url = models.URLField(max_length=255, blank=True, null=True)
    instagram_username = models.CharField(max_length=100, blank=True, null=True)
    twitter_username = models.CharField(max_length=100, blank=True, null=True)
    bluesky_handle = models.CharField(max_length=100, blank=True, null=True)
    threads_username = models.CharField(max_length=100, blank=True, null=True)
    
    google_code = models.CharField(max_length=255, blank=True, null=True)
    currency = models.CharField(max_length=10, default='USD')

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email

class Subscription(models.Model):
    SUBSCRIPTION_LEVELS = [
        ('free', 'Free'),
        ('basic', 'Basic'),
        ('premium', 'Premium'),
    ]
    BILLING_CHOICES = [
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ]

    PROCESSING_LIMITS = {
        'free': 5,        # 5 menu processings per month
        'basic': 25,      # 25 menu processings per month
        'premium': None   # Unlimited menu processings
    }
    
    total_processings = models.IntegerField(default=0, help_text="Total number of menu processings")
    last_processing_date = models.DateTimeField(null=True, blank=True)
    processings_this_month = models.IntegerField(default=0, help_text="Number of processings this month")
    last_month_reset = models.DateTimeField(null=True, blank=True)
    
    def reset_monthly_processings(self):
        """Reset the monthly processing count if we're in a new month"""
        now = timezone.now()
        if (not self.last_month_reset or 
            self.last_month_reset.month != now.month or 
            self.last_month_reset.year != now.year):
            self.processings_this_month = 0
            self.last_month_reset = now
            self.save()
    
    @property
    def monthly_processing_limit(self):
        return self.PROCESSING_LIMITS.get(self.level)
    
    def can_process_menu(self):
        """Check if the user can process another menu based on their subscription"""
        self.reset_monthly_processings()
        
        if self.level == 'premium':
            return True
            
        return self.processings_this_month < self.monthly_processing_limit
    
    def increment_processing_count(self):
        """Increment both total and monthly processing counts"""
        self.total_processings += 1
        self.processings_this_month += 1
        self.last_processing_date = timezone.now()
        self.save()

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscription')
    level = models.CharField(max_length=50, choices=SUBSCRIPTION_LEVELS, default='free')
    billing_cycle = models.CharField(max_length=50, choices=BILLING_CHOICES, default='monthly')
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.email} - {self.level}"

    def is_active(self):
        if self.end_date is None:
            return True
        return timezone.now() < self.end_date

class Menu(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    menu_data = models.JSONField(default=dict, help_text="Complete menu structure including categories and items")

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.user.email}"

    def ensure_default_category(self):
        """Ensure the menu has exactly one default category."""
        default_category = self.categories.filter(default=True).first()
        if not default_category:
            self.categories.create(
                name="Default Category",
                order=0,
                deletable=False,
                default=True
            )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.ensure_default_category()




class MenuImage(models.Model):
    IMAGE_TYPES = [
        ('menu', 'Menu Image'),
        ('general', 'General Image'),
    ]
    name = models.CharField(max_length=255, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    image = CloudinaryField(
        'image',
        folder='menu_images',
        resource_type='image',
        transformation={
            'quality': 'auto:good',
            'fetch_format': 'auto'
        }
    )
    public_id = models.CharField(max_length=255, unique=True, null=True, blank=True)  # Add public_id field
    image_type = models.CharField(max_length=10, choices=IMAGE_TYPES, default='general')
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    menu = models.ForeignKey('Menu', on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=255, blank=True, null=True)

    def get_cloudinary_url(self):
        return self.image.url

    def save(self, *args, **kwargs):
        # Set default name if none provided
        if not self.name and self.created_at:
            self.name = f"Image_{self.created_at.strftime('%Y%m%d')}_{self.id or 'new'}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name or str(self.id)


class MenuCategory(models.Model):
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=255)
    name_secondary = models.CharField(max_length=255, blank=True, null=True)
    order = models.IntegerField(default=0)
    deletable = models.BooleanField(default=True)  # Prevent deletion of certain categories
    default = models.BooleanField(default=False)  # Indicates the default category
    images = models.ManyToManyField(MenuImage, blank=True)  # Add images field

    class Meta:
        ordering = ['order']
        verbose_name_plural = 'Menu categories'

    def __str__(self):
        return f"{self.name} - {self.menu.name}"

class MenuItem(models.Model):
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE)
    category = models.ForeignKey(MenuCategory, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=255)
    title_secondary = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    description_secondary = models.TextField(blank=True, null=True)
    cost = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    order = models.IntegerField(default=0)
    images = models.ManyToManyField(MenuImage, blank=True)
    options = models.JSONField(blank=True, null=True, help_text="JSON field to store optional extras or variations")

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.title} - {self.menu.name}"

    def save(self, *args, **kwargs):
        # Automatically assign to the default category if no category is assigned
        if not self.category:
            default_category = self.menu.categories.filter(default=True).first()
            if default_category:
                self.category = default_category
        super().save(*args, **kwargs)

class MenuScan(models.Model):
    menu = models.ForeignKey('Menu', on_delete=models.CASCADE, related_name='scans')
    scanned_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, null=True, blank=True)
    referrer = models.URLField(max_length=500, null=True, blank=True)

    class Meta:
        ordering = ['-scanned_at']

    def __str__(self):
        return f"Scan of {self.menu.name} at {self.scanned_at}"
    
# models.py - Add these new models

from django.db import models
from cloudinary.models import CloudinaryField

class Template(models.Model):
    INDUSTRY_CHOICES = [
        ('restaurant', 'Restaurant'),
        ('cafe', 'Cafe'),
        ('bar', 'Bar'),
        ('food_truck', 'Food Truck'),
        ('other', 'Other'),
    ]
    
    STYLE_CHOICES = [
        ('modern', 'Modern'),
        ('classic', 'Classic'),
        ('minimal', 'Minimal'),
        ('elegant', 'Elegant'),
        ('bold', 'Bold'),
    ]

    # Existing fields
    name = models.CharField(max_length=100)
    description = models.TextField()
    thumbnail = CloudinaryField('thumbnail', folder='template_thumbnails')
    html_template = models.TextField(help_text="Base HTML template", blank=True, null=True)
    css_template = models.TextField(help_text="Base CSS styles", blank=True, null=True)
    js_template = models.TextField(blank=True, null=True, help_text="Optional JavaScript")

    industry_type = models.CharField(max_length=50, choices=INDUSTRY_CHOICES)
    style = models.CharField(max_length=50, choices=STYLE_CHOICES)
    is_premium = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({'Premium' if self.is_premium else 'Free'})"

    def get_normalized_name(self):
        """Normalize name to directory-safe format."""
        return re.sub(r'\s+', '_', self.name.lower())

    def get_template_path(self):
        """Get the base path for this template."""
        return f"menu_templates/{self.get_normalized_name()}/"

    def get_html_file(self):
        """Path to the HTML template file."""
        return f"{self.get_template_path()}template.html"

    def get_css_file(self):
        """Path to the CSS file."""
        return f"{self.get_template_path()}style.css"

    def get_js_file(self):
        """Path to the JS file."""
        return f"{self.get_template_path()}script.js"

    def get_config_file(self):
        """Path to the JSON config file."""
        return f"{self.get_template_path()}config.json"


class PublishedMenu(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE)
    template = models.ForeignKey(Template, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Template Customization
    custom_colors = models.JSONField(default=dict)
    custom_fonts = models.JSONField(default=dict)
    custom_css = models.TextField(blank=True, null=True)
    
    # Publishing Details
    slug = models.SlugField(max_length=100, unique=True, null=True, blank=True)
    custom_domain = models.CharField(max_length=255, unique=True, null=True, blank=True)
    is_custom_domain_verified = models.BooleanField(default=False)
    
    # Analytics and Tracking
    view_count = models.IntegerField(default=0)
    last_viewed_at = models.DateTimeField(null=True, blank=True)
    
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        unique_together = [['user', 'menu']]

    def __str__(self):
        return f"{self.menu.name} - {self.status}"

    def get_absolute_url(self):
        """
        Returns the URL for accessing the published menu.
        Prioritizes custom domain if verified, falls back to subdirectory URL.
        """
        if self.custom_domain and self.is_custom_domain_verified:
            return f"https://{self.custom_domain}"
        elif self.slug:
            # Use request.build_absolute_uri in views instead of hardcoding the domain
            return f"/m/{self.slug}"
        return None

    def save(self, *args, **kwargs):
        # Generate slug if not provided
        if not self.slug:
            base_slug = slugify(self.menu.name)
            slug = base_slug
            counter = 1
            
            # Ensure unique slug
            while PublishedMenu.objects.filter(slug=slug).exclude(id=self.id).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            
            self.slug = slug
            
        # Ensure status is set
        if not self.status:
            self.status = 'published'
            
        # Set published_at if publishing
        if self.status == 'published' and not self.published_at:
            self.published_at = timezone.now()
            
        super().save(*args, **kwargs)

    def publish(self):
        if self.status == 'draft':
            self.status = 'published'
            self.published_at = timezone.now()
            self.save()

    def unpublish(self):
        if self.status == 'published':
            self.status = 'draft'
            self.save()

    def get_menu_url(self, request=None):
        """
        Returns the full URL including domain for the menu.
        If request is provided, uses it to build the absolute URI.
        """
        if self.custom_domain and self.is_custom_domain_verified:
            return f"https://{self.custom_domain}"
        elif self.slug and request:
            return request.build_absolute_uri(self.get_absolute_url())
        elif self.slug:
            return self.get_absolute_url()
        return None

class TemplateAnalytics(models.Model):
    published_menu = models.ForeignKey(PublishedMenu, on_delete=models.CASCADE)
    date = models.DateField()
    view_count = models.IntegerField(default=0)
    unique_visitors = models.IntegerField(default=0)
    avg_time_on_page = models.DurationField(null=True)
    
    class Meta:
        unique_together = [['published_menu', 'date']]
        ordering = ['-date']

    def __str__(self):
        return f"{self.published_menu.menu.name} - {self.date}"
    
class MenuTemplate(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    html_content = models.TextField(help_text="HTML template content")
    css_content = models.TextField(help_text="CSS for styling the menu")
    js_content = models.TextField(blank=True, null=True, help_text="Optional JavaScript")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    