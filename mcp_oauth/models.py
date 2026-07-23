from django.db import models


class AccessTokenResource(models.Model):
    access_token = models.OneToOneField(
        'oauth2_provider.AccessToken',
        on_delete=models.CASCADE,
        related_name='mcp_resource_binding',
    )
    resource = models.URLField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'MCP access token resource binding'
        verbose_name_plural = 'MCP access token resource bindings'

    def __str__(self):
        return f'{self.resource} for token {self.access_token_id}'
