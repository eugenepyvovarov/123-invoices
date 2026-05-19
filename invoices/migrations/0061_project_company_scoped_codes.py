from collections import Counter

from django.core.exceptions import ValidationError
from django.db import migrations, models
import django.db.models.deletion


def backfill_project_issuer(apps, schema_editor):
    Project = apps.get_model('invoices', 'Project')
    Customer = apps.get_model('invoices', 'Customer')

    customer_issuers = dict(Customer.objects.values_list('id', 'issuer_id'))
    projects = list(Project.objects.values('id', 'customer_id', 'project_code'))

    scoped_codes = Counter()
    updates = []
    for project in projects:
        issuer_id = customer_issuers.get(project['customer_id'])
        if issuer_id:
            scoped_codes[(issuer_id, project['project_code'])] += 1
        updates.append(Project(id=project['id'], issuer_id=issuer_id))

    duplicate_codes = [
        project_code
        for (_issuer_id, project_code), count in scoped_codes.items()
        if count > 1
    ]
    if duplicate_codes:
        duplicate_list = ', '.join(sorted(set(duplicate_codes)))
        raise ValidationError(
            f'Duplicate project codes already exist within the same issuing company: {duplicate_list}'
        )

    if updates:
        Project.objects.bulk_update(updates, ['issuer'])


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0060_backuprun_trigger_source'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='issuer',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='projects',
                to='invoices.issuer',
            ),
        ),
        migrations.RunPython(backfill_project_issuer, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='project',
            name='project_code',
            field=models.CharField(max_length=50),
        ),
        migrations.AddConstraint(
            model_name='project',
            constraint=models.UniqueConstraint(
                fields=('issuer', 'project_code'),
                name='unique_project_code_per_issuer',
            ),
        ),
    ]
