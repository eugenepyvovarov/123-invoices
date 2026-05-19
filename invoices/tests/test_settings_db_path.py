from pathlib import Path

from django.test import SimpleTestCase

from app.settings import CONTAINER_DB_PATH, resolve_default_db_path, should_ignore_database_url


class ResolveDefaultDbPathTests(SimpleTestCase):
    def test_uses_container_db_path_for_containerized_runtime(self):
        resolved_path = resolve_default_db_path(environment={'INVOICES_CONTAINERIZED': '1'})

        self.assertEqual(resolved_path, CONTAINER_DB_PATH)

    def test_uses_repo_relative_db_path_outside_containerized_runtime(self):
        base_dir = Path('/tmp/invoices-project')

        resolved_path = resolve_default_db_path(base_dir=base_dir, environment={})

        self.assertEqual(resolved_path, base_dir / 'db/db.sqlite3')


class ShouldIgnoreDatabaseUrlTests(SimpleTestCase):
    def test_ignores_stale_tmp_sqlite_database_url_in_containerized_runtime(self):
        self.assertTrue(
            should_ignore_database_url(
                database_url='sqlite:////tmp/db.sqlite3',
                environment={'INVOICES_CONTAINERIZED': '1'},
            )
        )

    def test_keeps_tmp_sqlite_database_url_outside_containerized_runtime(self):
        self.assertFalse(
            should_ignore_database_url(
                database_url='sqlite:////tmp/db.sqlite3',
                environment={},
            )
        )

    def test_keeps_external_database_url_in_containerized_runtime(self):
        self.assertFalse(
            should_ignore_database_url(
                database_url='postgres://user:pass@example.com:5432/invoices',
                environment={'INVOICES_CONTAINERIZED': '1'},
            )
        )
