from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('oauth2_provider', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AccessTokenResource',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('resource', models.URLField(max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('access_token', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='mcp_resource_binding', to='oauth2_provider.accesstoken')),
            ],
            options={
                'verbose_name': 'MCP access token resource binding',
                'verbose_name_plural': 'MCP access token resource bindings',
            },
        ),
    ]
