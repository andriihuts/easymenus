# Generated by Django 5.1.3 on 2024-12-16 10:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('myapp', '0006_menucategory_default'),
    ]

    operations = [
        migrations.AddField(
            model_name='menuimage',
            name='public_id',
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
    ]
