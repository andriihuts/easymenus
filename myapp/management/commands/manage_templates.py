# myapp/management/commands/manage_templates.py

from django.core.management.base import BaseCommand
from myapp.models import Template
from django.db import transaction
import os
import json

class Command(BaseCommand):
    help = 'Manage menu templates'
    template_dir = 'myapp/templates/menu_templates'

    def add_arguments(self, parser):
        parser.add_argument('action', type=str, choices=['create', 'delete', 'list', 'sync'], 
                          help='Action to perform')
        parser.add_argument('--name', type=str, help='Template name (required for delete)')

    def handle(self, *args, **options):
        action = options['action']
        
        if action == 'sync':
            self.sync_templates()
        elif action == 'delete':
            if not options['name']:
                self.stderr.write('--name is required for delete action')
                return
            self.delete_template(options['name'])
        elif action == 'list':
            self.list_templates()

    def read_template_files(self, template_path):
        """Read template files from a directory."""
        try:
            with open(os.path.join(template_path, 'config.json'), 'r') as f:
                config = json.load(f)
            
            with open(os.path.join(template_path, 'template.html'), 'r') as f:
                html_content = f.read()
            
            with open(os.path.join(template_path, 'style.css'), 'r') as f:
                css_content = f.read()
            
            # JS is optional
            js_content = ''
            js_path = os.path.join(template_path, 'script.js')
            if os.path.exists(js_path):
                with open(js_path, 'r') as f:
                    js_content = f.read()
            
            return {
                'name': config.get('name'),
                'description': config.get('description', ''),
                'industry_type': config.get('industry_type', 'restaurant'),
                'style': config.get('style', 'modern'),
                'is_premium': config.get('is_premium', False),
                'html_template': html_content,
                'css_template': css_content,
                'js_template': js_content
            }
        except Exception as e:
            self.stderr.write(f'Error reading template {template_path}: {str(e)}')
            return None

    @transaction.atomic
    def sync_templates(self):
        """Sync templates from filesystem to database."""
        if not os.path.exists(self.template_dir):
            self.stderr.write(f'Template directory not found: {self.template_dir}')
            return

        # Keep track of processed templates
        processed_templates = set()

        # Process each template directory
        for template_name in os.listdir(self.template_dir):
            template_path = os.path.join(self.template_dir, template_name)
            
            if not os.path.isdir(template_path):
                continue

            template_data = self.read_template_files(template_path)
            if not template_data:
                continue

            try:
                template, created = Template.objects.update_or_create(
                    name=template_data['name'],
                    defaults={
                        'description': template_data['description'],
                        'industry_type': template_data['industry_type'],
                        'style': template_data['style'],
                        'is_premium': template_data['is_premium'],
                        'html_template': template_data['html_template'],
                        'css_template': template_data['css_template'],
                        'js_template': template_data['js_template'],
                    }
                )
                
                processed_templates.add(template_data['name'])
                status = 'Created' if created else 'Updated'
                self.stdout.write(self.style.SUCCESS(
                    f'{status} template "{template.name}"'
                ))
            
            except Exception as e:
                self.stderr.write(f'Error processing template {template_name}: {str(e)}')

        # Report templates that exist in DB but not in filesystem
        db_templates = Template.objects.exclude(name__in=processed_templates)
        if db_templates.exists():
            self.stdout.write('\nTemplates in database but not in filesystem:')
            for template in db_templates:
                self.stdout.write(f'- {template.name}')

    def delete_template(self, name):
        try:
            template = Template.objects.get(name=name)
            template.delete()
            self.stdout.write(self.style.SUCCESS(
                f'Successfully deleted template "{name}"'
            ))
        except Template.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                f'Template "{name}" does not exist'
            ))

    def list_templates(self):
        # List both filesystem and database templates
        self.stdout.write('\nTemplates in filesystem:')
        if os.path.exists(self.template_dir):
            for template_name in os.listdir(self.template_dir):
                template_path = os.path.join(self.template_dir, template_name)
                if os.path.isdir(template_path):
                    try:
                        with open(os.path.join(template_path, 'config.json'), 'r') as f:
                            config = json.load(f)
                            self.stdout.write(f'- {config.get("name", template_name)}')
                    except:
                        self.stdout.write(f'- {template_name} (invalid config)')
        else:
            self.stdout.write('Template directory not found')

        self.stdout.write('\nTemplates in database:')
        templates = Template.objects.all()
        if templates:
            for template in templates:
                self.stdout.write(f'- {template.name}')
                self.stdout.write(f'  Style: {template.style}')
                self.stdout.write(f'  Industry: {template.industry_type}')
                self.stdout.write(f'  Premium: {template.is_premium}')
        else:
            self.stdout.write('No templates found in database')