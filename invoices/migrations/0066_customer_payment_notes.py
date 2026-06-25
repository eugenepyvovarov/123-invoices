from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0065_add_incoming_candidate_rejected_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='customer',
            name='payment_notes',
            field=models.TextField(blank=True, default=''),
        ),
    ]
