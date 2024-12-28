# Generated by Django 5.1.3 on 2024-12-17 15:25

import cloudinary.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('myapp', '0011_remove_user_business_location_user_address_line1_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Template',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField()),
                ('thumbnail', cloudinary.models.CloudinaryField(max_length=255, verbose_name='thumbnail')),
                ('html_template', models.TextField(help_text='Base HTML template')),
                ('css_template', models.TextField(help_text='Base CSS styles')),
                ('js_template', models.TextField(blank=True, help_text='Optional JavaScript', null=True)),
                ('industry_type', models.CharField(choices=[('restaurant', 'Restaurant'), ('cafe', 'Cafe'), ('bar', 'Bar'), ('food_truck', 'Food Truck'), ('other', 'Other')], max_length=50)),
                ('style', models.CharField(choices=[('modern', 'Modern'), ('classic', 'Classic'), ('minimal', 'Minimal'), ('elegant', 'Elegant'), ('bold', 'Bold')], max_length=50)),
                ('is_premium', models.BooleanField(default=False)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='PublishedMenu',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('published', 'Published'), ('archived', 'Archived')], default='draft', max_length=20)),
                ('custom_css', models.TextField(blank=True, null=True)),
                ('custom_colors', models.JSONField(default=dict)),
                ('custom_fonts', models.JSONField(default=dict)),
                ('subdomain', models.CharField(blank=True, max_length=100, null=True, unique=True)),
                ('custom_domain', models.CharField(blank=True, max_length=255, null=True, unique=True)),
                ('is_custom_domain_verified', models.BooleanField(default=False)),
                ('view_count', models.IntegerField(default=0)),
                ('last_viewed_at', models.DateTimeField(blank=True, null=True)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('menu', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='myapp.menu')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('template', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='myapp.template')),
            ],
            options={
                'ordering': ['-updated_at'],
                'unique_together': {('user', 'menu')},
            },
        ),
        migrations.CreateModel(
            name='TemplateAnalytics',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('view_count', models.IntegerField(default=0)),
                ('unique_visitors', models.IntegerField(default=0)),
                ('avg_time_on_page', models.DurationField(null=True)),
                ('published_menu', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='myapp.publishedmenu')),
            ],
            options={
                'ordering': ['-date'],
                'unique_together': {('published_menu', 'date')},
            },
        ),
    ]
