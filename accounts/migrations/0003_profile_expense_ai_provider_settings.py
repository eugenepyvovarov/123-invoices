from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_profile_default_company'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='expense_ai_provider_base_url',
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='expense_ai_model_name',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='profile',
            name='expense_ai_api_key',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
