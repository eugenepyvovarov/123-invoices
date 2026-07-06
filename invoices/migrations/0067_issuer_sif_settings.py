from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def create_default_sif_settings(apps, schema_editor):
    Issuer = apps.get_model('invoices', 'Issuer')
    IssuerSifSettings = apps.get_model('invoices', 'IssuerSifSettings')
    now = timezone.now()
    IssuerSifSettings.objects.bulk_create(
        [
            IssuerSifSettings(issuer=issuer, created_at=now, updated_at=now)
            for issuer in Issuer.objects.filter(sif_settings__isnull=True)
        ]
    )


def delete_default_sif_settings(apps, schema_editor):
    IssuerSifSettings = apps.get_model('invoices', 'IssuerSifSettings')
    IssuerSifSettings.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0066_customer_payment_notes'),
    ]

    operations = [
        migrations.CreateModel(
            name='IssuerSifSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tax_country', models.CharField(blank=True, choices=[('', 'Unspecified'), ('ES', 'Spain'), ('OTHER', 'Other country')], default='', help_text='Explicit issuer/establishment tax country. Spain (ES) makes SIF applicable.', max_length=16)),
                ('enabled', models.BooleanField(default=False)),
                ('mode', models.CharField(choices=[('VERI_FACTU', 'VERI*FACTU'), ('NO_VERI_FACTU', 'No VERI*FACTU')], default='VERI_FACTU', max_length=16)),
                ('aeat_environment', models.CharField(choices=[('TEST', 'AEAT test'), ('PRODUCTION', 'AEAT production')], default='TEST', max_length=16)),
                ('taxpayer_role', models.CharField(choices=[('CORPORATE', 'SL / corporate taxpayer'), ('AUTONOMO', 'Autónomo / individual taxpayer'), ('OTHER', 'Other covered taxpayer')], default='OTHER', max_length=16)),
                ('deadline_category', models.CharField(choices=[('CORPORATE', 'Corporate Tax deadline'), ('AUTONOMO_OTHER', 'Autónomo / other taxpayer deadline')], default='AUTONOMO_OTHER', max_length=16)),
                ('software_name', models.CharField(blank=True, default='', max_length=128)),
                ('software_version', models.CharField(blank=True, default='', max_length=64)),
                ('software_code', models.CharField(blank=True, default='', max_length=64)),
                ('certificate_reference', models.CharField(blank=True, default='', help_text='Non-secret certificate label or external reference only.', max_length=128)),
                ('operational_status', models.CharField(choices=[('NOT_READY', 'Not ready'), ('READY', 'Ready'), ('SUSPENDED', 'Suspended')], default='NOT_READY', max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('issuer', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='sif_settings', to='invoices.issuer')),
            ],
            options={
                'verbose_name': 'Issuer SIF settings',
                'verbose_name_plural': 'Issuer SIF settings',
                'ordering': ['issuer'],
            },
        ),
        migrations.RunPython(create_default_sif_settings, delete_default_sif_settings),
    ]
