from datetime import date

from django.test import RequestFactory, SimpleTestCase

from invoices.utils.date_filters import (
    DEFAULT_DATE_RANGE_KEY,
    ROLLING_YEAR_DATE_RANGE_KEY,
    get_date_range_bounds,
    get_date_range_options,
    get_global_date_filter,
)


class DateFilterTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_rolling_year_bounds_include_previous_twelve_months_and_current_month(self):
        start, end = get_date_range_bounds(ROLLING_YEAR_DATE_RANGE_KEY, date(2026, 6, 5))

        self.assertEqual(start, date(2025, 6, 1))
        self.assertEqual(end, date(2026, 6, 30))

    def test_rolling_year_bounds_handle_year_boundary(self):
        start, end = get_date_range_bounds(ROLLING_YEAR_DATE_RANGE_KEY, date(2026, 1, 15))

        self.assertEqual(start, date(2025, 1, 1))
        self.assertEqual(end, date(2026, 1, 31))

    def test_date_range_options_include_rolling_year_metadata(self):
        options = get_date_range_options(date(2026, 6, 5))
        rolling_year = options[0]

        self.assertEqual(rolling_year['value'], ROLLING_YEAR_DATE_RANGE_KEY)
        self.assertEqual(rolling_year['label'], 'Rolling Year')
        self.assertEqual(rolling_year['range_display'], '01 Jun 2025 - 30 Jun 2026')
        self.assertEqual(
            [option['value'] for option in options[1:]],
            ['this_month', 'last_month', 'ytd', 'last_year', 'all'],
        )

    def test_global_date_filter_defaults_to_rolling_year(self):
        request = self.factory.get('/dashboard/')
        request.session = {}

        filter_context = get_global_date_filter(request)

        self.assertEqual(DEFAULT_DATE_RANGE_KEY, ROLLING_YEAR_DATE_RANGE_KEY)
        self.assertEqual(filter_context['key'], ROLLING_YEAR_DATE_RANGE_KEY)
        self.assertEqual(filter_context['label'], 'Rolling Year')

    def test_global_date_filter_falls_back_to_rolling_year_for_invalid_stored_selection(self):
        request = self.factory.get('/dashboard/')
        request.session = {'global_date_range': 'not-a-real-period'}

        filter_context = get_global_date_filter(request)

        self.assertEqual(filter_context['key'], ROLLING_YEAR_DATE_RANGE_KEY)

    def test_global_date_filter_preserves_valid_explicit_selection(self):
        request = self.factory.get('/dashboard/', {'date_range': 'all'})
        request.session = {}

        filter_context = get_global_date_filter(request)

        self.assertEqual(filter_context['key'], 'all')
        self.assertEqual(request.session['global_date_range'], 'all')
