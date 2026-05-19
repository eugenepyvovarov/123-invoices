from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


WISE_MAPPING_NAME = 'Wise CSV expense import'
WISE_HEADERS = [
    'TransferWise ID',
    'Date Time',
    'Amount',
    'Currency',
    'Description',
    'Payment Reference',
    'Transaction Type',
    'Transaction Details Type',
]
WISE_MAPPING_JSON = {
    'transaction_id': 'TransferWise ID',
    'paid_date': 'Date Time',
    'amount': 'Amount',
    'currency': 'Currency',
    'description': ['Description', 'Payment Reference'],
    'row_type': 'Transaction Type',
    'details_type': 'Transaction Details Type',
    'date_formats': ['%d-%m-%Y %H:%M:%S.%f', '%d-%m-%Y %H:%M:%S'],
    'amount_mode': 'absolute',
}
WISE_DEFAULT_ROW_SELECTION_RULES = {
    'include': [{'column': 'Transaction Type', 'equals': 'DEBIT'}],
    'exclude': [{'column': 'Transaction Details Type', 'equals': 'CONVERSION'}],
}


def normalized_header_signature(headers):
    normalized = [" ".join((header or "").lstrip("\ufeff").strip().casefold().split()) for header in headers]
    return "|".join(sorted(header for header in normalized if header))


def seed_wise_mapping(apps, schema_editor):
    ImportMapping = apps.get_model('invoices', 'ImportMapping')
    defaults = {
        'owner': None,
        'normalized_header_signature': normalized_header_signature(WISE_HEADERS),
        'mapping_json': WISE_MAPPING_JSON,
        'default_row_selection_rules': WISE_DEFAULT_ROW_SELECTION_RULES,
        'read_only': True,
    }
    mapping, _ = ImportMapping.objects.get_or_create(
        scope='global',
        name=WISE_MAPPING_NAME,
        defaults=defaults,
    )
    changed = False
    for field, value in defaults.items():
        if getattr(mapping, field) != value:
            setattr(mapping, field, value)
            changed = True
    if changed:
        mapping.save(update_fields=list(defaults.keys()))


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('invoices', '0060_backuprun_trigger_source'),
    ]

    operations = [
        migrations.CreateModel(
            name='ImportMapping',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('scope', models.CharField(choices=[('global', 'Global'), ('user', 'User')], max_length=16)),
                ('name', models.CharField(max_length=100)),
                ('normalized_header_signature', models.TextField()),
                ('mapping_json', models.JSONField(default=dict)),
                ('default_row_selection_rules', models.JSONField(blank=True, default=dict)),
                ('read_only', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='expense_import_mappings', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['scope', 'name'],
            },
        ),
        migrations.CreateModel(
            name='ImportBatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('uploaded', 'Uploaded'), ('mapped', 'Mapped'), ('imported', 'Imported'), ('failed', 'Failed')], default='uploaded', max_length=16)),
                ('source_filename', models.CharField(blank=True, max_length=255)),
                ('normalized_header_signature', models.TextField(blank=True)),
                ('raw_headers', models.JSONField(blank=True, default=list)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('issuer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='expense_import_batches', to='invoices.issuer')),
                ('mapping', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='import_batches', to='invoices.importmapping')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='expense_import_batches', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.CreateModel(
            name='ImportPreviewRow',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('row_index', models.PositiveIntegerField()),
                ('raw_data', models.JSONField(default=dict)),
                ('mapped_data', models.JSONField(blank=True, default=dict)),
                ('default_selected', models.BooleanField(default=True)),
                ('selected', models.BooleanField(default=True)),
                ('validation_errors', models.JSONField(blank=True, default=list)),
                ('fingerprint', models.CharField(blank=True, max_length=128)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('batch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='preview_rows', to='invoices.importbatch')),
            ],
            options={
                'ordering': ['row_index'],
            },
        ),
        migrations.AddConstraint(
            model_name='importmapping',
            constraint=models.CheckConstraint(check=(models.Q(('owner__isnull', True), ('scope', 'global')) | models.Q(('owner__isnull', False), ('scope', 'user'))), name='import_mapping_scope_owner_valid'),
        ),
        migrations.AddConstraint(
            model_name='importmapping',
            constraint=models.UniqueConstraint(condition=models.Q(('scope', 'global')), fields=('name',), name='unique_global_import_mapping_name'),
        ),
        migrations.AddConstraint(
            model_name='importmapping',
            constraint=models.UniqueConstraint(condition=models.Q(('scope', 'user')), fields=('owner', 'name'), name='unique_user_import_mapping_name'),
        ),
        migrations.AddConstraint(
            model_name='importpreviewrow',
            constraint=models.UniqueConstraint(fields=('batch', 'row_index'), name='unique_import_preview_row_index'),
        ),
        migrations.RunPython(seed_wise_mapping, migrations.RunPython.noop),
    ]
