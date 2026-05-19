from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0046_backfill_invoice_cached_amounts'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='payment_term',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='invoices', to='invoices.paymentterm'),
        ),
    ]
