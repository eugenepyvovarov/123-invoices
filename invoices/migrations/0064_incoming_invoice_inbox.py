from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import invoices.models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('invoices', '0063_issuer_bank_accounts'),
    ]

    operations = [
        migrations.CreateModel(
            name='IncomingEmailSource',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider', models.CharField(choices=[('imap', 'IMAP')], default='imap', max_length=16)),
                ('display_name', models.CharField(max_length=100)),
                ('email_address', models.EmailField(max_length=254)),
                ('is_enabled', models.BooleanField(default=True)),
                ('folder', models.CharField(default='INBOX', max_length=255)),
                ('polling_query', models.CharField(blank=True, max_length=255)),
                ('credential_reference', models.CharField(blank=True, max_length=255)),
                ('provider_state', models.JSONField(blank=True, default=dict)),
                ('last_seen_message_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('issuer', models.ForeignKey(blank=True, help_text='Optional issuer for a company-specific mailbox source.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='incoming_email_sources', to='invoices.issuer')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='incoming_email_sources', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['display_name', 'id'],
            },
        ),
        migrations.CreateModel(
            name='IssuerEmailRoutingRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('recipient_aliases', models.JSONField(blank=True, default=list)),
                ('delivered_to_addresses', models.JSONField(blank=True, default=list)),
                ('legal_names', models.JSONField(blank=True, default=list)),
                ('tax_identifiers', models.JSONField(blank=True, default=list)),
                ('keywords', models.JSONField(blank=True, default=list)),
                ('confidence_threshold', models.DecimalField(decimal_places=2, default=Decimal('0.80'), max_digits=5)),
                ('auto_assign_enabled', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('issuer', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='incoming_email_routing_rule', to='invoices.issuer')),
            ],
            options={
                'ordering': ['issuer'],
            },
        ),
        migrations.CreateModel(
            name='IncomingInvoiceCandidate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('new', 'New'), ('needs_review', 'Needs review'), ('ready', 'Ready'), ('reviewed_unpaid', 'Reviewed/unpaid'), ('converted', 'Converted'), ('not_invoice', 'Not an invoice'), ('duplicate', 'Duplicate'), ('needs_fetch', 'Needs manual fetch'), ('error', 'Error')], default='new', max_length=32)),
                ('provider_message_id', models.CharField(max_length=255)),
                ('provider_thread_id', models.CharField(blank=True, max_length=255)),
                ('from_name', models.CharField(blank=True, max_length=255)),
                ('from_email', models.EmailField(blank=True, max_length=254)),
                ('to_addresses', models.JSONField(blank=True, default=list)),
                ('cc_addresses', models.JSONField(blank=True, default=list)),
                ('delivered_to_addresses', models.JSONField(blank=True, default=list)),
                ('subject', models.CharField(blank=True, max_length=500)),
                ('received_at', models.DateTimeField()),
                ('body_text', models.TextField(blank=True)),
                ('body_html', models.TextField(blank=True)),
                ('extracted_metadata', models.JSONField(blank=True, default=dict)),
                ('detection_metadata', models.JSONField(blank=True, default=dict)),
                ('duplicate_metadata', models.JSONField(blank=True, default=dict)),
                ('fingerprint', models.CharField(blank=True, max_length=128)),
                ('raw_provider_metadata', models.JSONField(blank=True, default=dict)),
                ('reviewed_metadata', models.JSONField(blank=True, default=dict)),
                ('conversion_limitation_message', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('confirmed_issuer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='confirmed_incoming_invoice_candidates', to='invoices.issuer')),
                ('converted_expense', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='incoming_invoice_candidate', to='invoices.expense')),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='candidates', to='invoices.incomingemailsource')),
                ('suggested_issuer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='suggested_incoming_invoice_candidates', to='invoices.issuer')),
            ],
            options={
                'ordering': ['-received_at', '-id'],
            },
        ),
        migrations.CreateModel(
            name='IncomingInvoiceArtifact',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('attachment', 'Attachment'), ('email_body_pdf', 'Email body PDF'), ('inline_image', 'Inline image'), ('other', 'Other')], default='attachment', max_length=32)),
                ('original_filename', models.CharField(blank=True, max_length=255)),
                ('content_type', models.CharField(blank=True, max_length=255)),
                ('size', models.PositiveBigIntegerField(default=0)),
                ('sha256', models.CharField(max_length=64)),
                ('file', models.FileField(upload_to=invoices.models.incoming_invoice_artifact_upload_path)),
                ('extracted_text', models.TextField(blank=True)),
                ('parsed_metadata', models.JSONField(blank=True, default=dict)),
                ('is_invoice_like', models.BooleanField(default=False)),
                ('invoice_confidence', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=5)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('candidate', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='artifacts', to='invoices.incominginvoicecandidate')),
            ],
            options={
                'ordering': ['candidate', 'id'],
            },
        ),
        migrations.AddField(
            model_name='incominginvoicecandidate',
            name='generated_body_pdf_artifact',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='body_pdf_for_candidates', to='invoices.incominginvoiceartifact'),
        ),
        migrations.AddField(
            model_name='incominginvoicecandidate',
            name='selected_artifact',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='selected_for_candidates', to='invoices.incominginvoiceartifact'),
        ),
        migrations.AddIndex(
            model_name='incomingemailsource',
            index=models.Index(fields=['provider', 'is_enabled'], name='incoming_source_provider_idx'),
        ),
        migrations.AddIndex(
            model_name='incomingemailsource',
            index=models.Index(fields=['issuer', 'is_enabled'], name='incoming_source_issuer_idx'),
        ),
        migrations.AddIndex(
            model_name='issueremailroutingrule',
            index=models.Index(fields=['issuer', 'auto_assign_enabled'], name='issuer_routing_enabled_idx'),
        ),
        migrations.AddConstraint(
            model_name='incominginvoicecandidate',
            constraint=models.UniqueConstraint(fields=('source', 'provider_message_id'), name='uniq_inc_cand_source_msg'),
        ),
        migrations.AddIndex(
            model_name='incominginvoicecandidate',
            index=models.Index(fields=['status', 'received_at'], name='inc_cand_status_date_idx'),
        ),
        migrations.AddIndex(
            model_name='incominginvoicecandidate',
            index=models.Index(fields=['suggested_issuer', 'status'], name='inc_cand_suggested_idx'),
        ),
        migrations.AddIndex(
            model_name='incominginvoicecandidate',
            index=models.Index(fields=['confirmed_issuer', 'status'], name='inc_cand_confirmed_idx'),
        ),
        migrations.AddIndex(
            model_name='incominginvoicecandidate',
            index=models.Index(fields=['source', 'received_at'], name='inc_cand_source_date_idx'),
        ),
        migrations.AddIndex(
            model_name='incominginvoicecandidate',
            index=models.Index(fields=['fingerprint'], name='inc_cand_fingerprint_idx'),
        ),
        migrations.AddConstraint(
            model_name='incominginvoiceartifact',
            constraint=models.UniqueConstraint(fields=('candidate', 'sha256'), name='uniq_inc_art_cand_hash'),
        ),
        migrations.AddIndex(
            model_name='incominginvoiceartifact',
            index=models.Index(fields=['sha256'], name='incoming_artifact_hash_idx'),
        ),
        migrations.AddIndex(
            model_name='incominginvoiceartifact',
            index=models.Index(fields=['kind', 'is_invoice_like'], name='incoming_artifact_kind_idx'),
        ),
    ]
