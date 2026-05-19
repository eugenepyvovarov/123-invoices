from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0034_expense'),
    ]

    operations = [
        migrations.CreateModel(
            name='InvoiceFilterView',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=64)),
                ('query', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('issuer', models.ForeignKey(on_delete=models.CASCADE, related_name='invoice_filter_views', to='invoices.issuer')),
            ],
            options={
                'ordering': ['name'],
                'unique_together': {('issuer', 'name')},
            },
        ),
    ]
