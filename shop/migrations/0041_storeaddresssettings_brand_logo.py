from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0040_homenewsticker'),
    ]

    operations = [
        migrations.AddField(
            model_name='storeaddresssettings',
            name='brand_logo',
            field=models.ImageField(blank=True, null=True, upload_to='store/logos/'),
        ),
    ]
