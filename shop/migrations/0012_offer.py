# Generated manually for the Offer Management module.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0011_homesection_homesectioncategory_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Offer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=160)),
                ('subtitle', models.CharField(blank=True, default='', max_length=180)),
                ('description', models.TextField()),
                ('banner_image', models.ImageField(upload_to='offers/%Y/%m/')),
                ('button_text', models.CharField(default='Shop Now', max_length=60)),
                ('redirect_type', models.CharField(choices=[('category', 'Category'), ('product', 'Product'), ('external_url', 'External URL'), ('page', 'Page')], max_length=20)),
                ('customer_page', models.CharField(blank=True, choices=[('/', 'Home'), ('/#collection', 'Shop'), ('/#new-arrivals', 'New Arrivals'), ('/#collections', 'Collections'), ('/#cart', 'Cart')], default='', max_length=60)),
                ('external_url', models.URLField(blank=True, default='')),
                ('display_priority_pc', models.PositiveIntegerField(default=10)),
                ('display_priority_mobile', models.PositiveIntegerField(blank=True, null=True)),
                ('status', models.CharField(choices=[('active', 'Active'), ('inactive', 'Inactive')], default='active', max_length=20)),
                ('start_at', models.DateTimeField(blank=True, null=True)),
                ('end_at', models.DateTimeField(blank=True, null=True)),
                ('no_expiry', models.BooleanField(default=False)),
                ('show_as_popup', models.BooleanField(default=False)),
                ('display_on_home', models.BooleanField(default=True)),
                ('display_on_offer_page', models.BooleanField(default=True)),
                ('popup_title', models.CharField(blank=True, default='', max_length=160)),
                ('popup_description', models.TextField(blank=True, default='')),
                ('popup_image', models.ImageField(blank=True, null=True, upload_to='offers/popup/%Y/%m/')),
                ('popup_button_text', models.CharField(blank=True, default='', max_length=60)),
                ('popup_display_mode', models.CharField(choices=[('once', 'Display once per user'), ('every_visit', 'Display every visit')], default='once', max_length=20)),
                ('show_close_button', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('category', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='offers', to='shop.category')),
                ('product', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='offers', to='shop.product')),
            ],
            options={
                'db_table': 'shop_offers',
                'ordering': ['display_priority_pc', 'id'],
            },
        ),
    ]
