import json
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]


class SettingsConfigTests(TestCase):
    def run_settings_subprocess(self, env_updates, expression):
        env = os.environ.copy()
        for key in ("DATABASE_URL", "DB_PATH", "INVOICES_CONTAINERIZED"):
            env.pop(key, None)

        env.update(
            {
                "SECRET_KEY": "test-secret",
                "DEBUG": "0",
                **env_updates,
            }
        )

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import json; import app.settings as s; "
                    f"print(json.dumps({expression}))"
                ),
            ],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

        return json.loads(result.stdout)

    def test_csrf_trusted_origins_include_env_values_and_render_hostname(self):
        if importlib.util.find_spec("environ") is None:
            self.skipTest("django-environ is not installed in this interpreter")

        payload = self.run_settings_subprocess(
            {
                "DEBUG": "1",
                "ALLOWED_HOSTS": "127.0.0.1,localhost",
                "CSRF_TRUSTED_ORIGINS": "https://invoices.ultramac.home,https://custom.example",
                "RENDER_EXTERNAL_HOSTNAME": "invoices.ultramac.work",
            },
            "{'csrf': s.CSRF_TRUSTED_ORIGINS, 'hosts': s.ALLOWED_HOSTS}",
        )

        self.assertEqual(
            payload["csrf"],
            [
                "https://invoices.ultramac.home",
                "https://custom.example",
                "https://invoices.ultramac.work",
            ],
        )
        self.assertIn("invoices.ultramac.work", payload["hosts"])

    def test_containerized_runtime_preserves_explicit_postgres_database_url(self):
        if importlib.util.find_spec("environ") is None:
            self.skipTest("django-environ is not installed in this interpreter")

        payload = self.run_settings_subprocess(
            {
                "INVOICES_CONTAINERIZED": "1",
                "DATABASE_URL": "postgres://dbuser:dbpass@example.com:5432/invoices",
            },
            "s.DATABASES['default']",
        )

        self.assertEqual(payload["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(payload["NAME"], "invoices")
        self.assertEqual(payload["USER"], "dbuser")
        self.assertEqual(payload["PASSWORD"], "dbpass")
        self.assertEqual(payload["HOST"], "example.com")
        self.assertEqual(payload["PORT"], 5432)

    def test_containerized_runtime_defaults_to_mounted_sqlite_path(self):
        if importlib.util.find_spec("environ") is None:
            self.skipTest("django-environ is not installed in this interpreter")

        payload = self.run_settings_subprocess(
            {
                "INVOICES_CONTAINERIZED": "1",
            },
            "s.DATABASES['default']",
        )

        self.assertEqual(payload["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(payload["NAME"], "/app/db/db.sqlite3")

    def test_containerized_runtime_ignores_stale_tmp_sqlite_database_url(self):
        if importlib.util.find_spec("environ") is None:
            self.skipTest("django-environ is not installed in this interpreter")

        payload = self.run_settings_subprocess(
            {
                "INVOICES_CONTAINERIZED": "1",
                "DATABASE_URL": "sqlite:////tmp/db.sqlite3",
            },
            "s.DATABASES['default']",
        )

        self.assertEqual(payload["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(payload["NAME"], "/app/db/db.sqlite3")

    def test_containerized_runtime_keeps_db_path_override_for_startup(self):
        if importlib.util.find_spec("environ") is None:
            self.skipTest("django-environ is not installed in this interpreter")

        payload = self.run_settings_subprocess(
            {
                "INVOICES_CONTAINERIZED": "1",
                "DB_PATH": "/app/db/custom.sqlite3",
                "DATABASE_URL": "sqlite:////tmp/db.sqlite3",
            },
            "s.DATABASES['default']",
        )

        self.assertEqual(payload["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(payload["NAME"], "/app/db/custom.sqlite3")
