from django.test import TestCase
from django.urls import reverse


class ApiSchemaTests(TestCase):
    def test_openapi_schema_generation_succeeds(self):
        response = self.client.get(reverse('api:schema'), HTTP_ACCEPT='application/json')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('openapi', payload)
        self.assertIn('/api/invoices/', payload['paths'])
        self.assertIn('BearerAuth', payload['components']['securitySchemes'])
