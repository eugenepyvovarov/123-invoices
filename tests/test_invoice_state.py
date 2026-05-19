from datetime import date
from decimal import Decimal
from unittest import TestCase

from invoices.services.invoice_state import (
    IS_OVERDUE_ANNOTATION,
    coerce_amount_due,
    is_invoice_overdue,
    overdue_boundary,
    overdue_boundary_date,
    overdue_read_paths,
    overdue_q,
)

try:
    from django.db.models import BooleanField, Case
    from invoices.services.invoice_state import annotate_is_overdue, overdue_annotation
    from invoices.models import Invoice
except ModuleNotFoundError:
    BooleanField = None
    Case = None
    annotate_is_overdue = None
    overdue_annotation = None
    Invoice = None


class InvoiceStateTests(TestCase):
    @staticmethod
    def assert_q_children_equal(actual_children, expected_children):
        normalize = lambda items: sorted(items, key=lambda item: repr(item))
        TestCase().assertEqual(normalize(actual_children), normalize(expected_children))

    def test_coerce_amount_due_defaults_blank_values_to_zero(self):
        self.assertEqual(coerce_amount_due(None), Decimal('0'))
        self.assertEqual(coerce_amount_due(''), Decimal('0'))

    def test_coerce_amount_due_preserves_decimal_values(self):
        amount_due = Decimal('10.50')

        self.assertIs(coerce_amount_due(amount_due), amount_due)

    def test_is_invoice_overdue_when_due_date_is_before_today_and_amount_due_is_positive(self):
        self.assertTrue(
            is_invoice_overdue(
                due_date=date(2026, 3, 23),
                amount_due='10.00',
                today=date(2026, 3, 24),
            )
        )

    def test_is_invoice_overdue_is_false_when_due_date_is_today(self):
        self.assertFalse(
            is_invoice_overdue(
                due_date=date(2026, 3, 24),
                amount_due='10.00',
                today=date(2026, 3, 24),
            )
        )

    def test_is_invoice_overdue_is_false_when_due_date_is_after_today(self):
        self.assertFalse(
            is_invoice_overdue(
                due_date=date(2026, 3, 25),
                amount_due='10.00',
                today=date(2026, 3, 24),
            )
        )

    def test_is_invoice_overdue_is_false_when_amount_due_is_zero(self):
        self.assertFalse(
            is_invoice_overdue(
                due_date=date(2026, 3, 23),
                amount_due='0.00',
                today=date(2026, 3, 24),
            )
        )

    def test_is_invoice_overdue_is_false_when_amount_due_is_negative(self):
        self.assertFalse(
            is_invoice_overdue(
                due_date=date(2026, 3, 23),
                amount_due='-5.00',
                today=date(2026, 3, 24),
            )
        )

    def test_is_invoice_overdue_is_false_when_amount_due_is_invalid(self):
        self.assertFalse(
            is_invoice_overdue(
                due_date=date(2026, 3, 23),
                amount_due='not-a-number',
                today=date(2026, 3, 24),
            )
        )

    def test_is_invoice_overdue_is_false_when_due_date_is_missing(self):
        self.assertFalse(
            is_invoice_overdue(
                due_date=None,
                amount_due='10.00',
                today=date(2026, 3, 24),
            )
        )

    def test_overdue_boundary_date_returns_explicit_today(self):
        self.assertEqual(overdue_boundary_date(today=date(2026, 3, 24)), date(2026, 3, 24))

    def test_overdue_boundary_reuses_same_today_for_match_and_query(self):
        boundary = overdue_boundary(today=date(2026, 3, 24))

        self.assertTrue(
            boundary.matches(
                due_date=date(2026, 3, 23),
                amount_due='10.00',
            )
        )

        if Case is None:
            self.skipTest('Django is not installed in the validation environment')

        overdue_filter = boundary.q(prefix='invoice__')
        self.assert_q_children_equal(
            overdue_filter.children,
            [
                ('invoice__due_date__lt', date(2026, 3, 24)),
                ('invoice__amount_due__gt', Decimal('0')),
            ],
        )

    def test_overdue_boundary_due_date_lookup_reuses_today_cutoff_with_prefix(self):
        boundary = overdue_boundary(today=date(2026, 3, 24))

        self.assertEqual(
            boundary.due_date_lookup(prefix='invoice__'),
            ('invoice__due_date__lt', date(2026, 3, 24)),
        )

    def test_overdue_boundary_is_past_due_is_false_when_due_date_is_today(self):
        boundary = overdue_boundary(today=date(2026, 3, 24))

        self.assertFalse(boundary.is_past_due(date(2026, 3, 24)))

    def test_overdue_boundary_matches_is_false_when_due_date_is_future(self):
        boundary = overdue_boundary(today=date(2026, 3, 24))

        self.assertFalse(
            boundary.matches(
                due_date=date(2026, 3, 25),
                amount_due=Decimal('10.00'),
            )
        )

    def test_overdue_boundary_matches_is_false_when_due_date_is_missing(self):
        boundary = overdue_boundary(today=date(2026, 3, 24))

        self.assertFalse(
            boundary.matches(
                due_date=None,
                amount_due='10.00',
            )
        )

    def test_is_invoice_overdue_uses_explicit_boundary_over_today_override(self):
        boundary = overdue_boundary(today=date(2026, 3, 24))

        self.assertTrue(
            is_invoice_overdue(
                due_date=date(2026, 3, 23),
                amount_due='10.00',
                today=date(2026, 3, 25),
                boundary=boundary,
            )
        )

    def test_overdue_boundary_matches_is_false_when_amount_due_is_blank(self):
        boundary = overdue_boundary(today=date(2026, 3, 24))

        self.assertFalse(
            boundary.matches(
                due_date=date(2026, 3, 23),
                amount_due='',
            )
        )

    def test_overdue_q_uses_shared_due_today_boundary(self):
        if Case is None:
            self.skipTest('Django is not installed in the validation environment')

        overdue_filter = overdue_q(today=date(2026, 3, 24))

        self.assert_q_children_equal(
            overdue_filter.children,
            [
                ('due_date__lt', date(2026, 3, 24)),
                ('amount_due__gt', Decimal('0')),
            ],
        )

    def test_overdue_q_uses_explicit_boundary_over_today_override(self):
        if Case is None:
            self.skipTest('Django is not installed in the validation environment')

        overdue_filter = overdue_q(
            today=date(2026, 3, 25),
            boundary=overdue_boundary(today=date(2026, 3, 24)),
        )

        self.assert_q_children_equal(
            overdue_filter.children,
            [
                ('due_date__lt', date(2026, 3, 24)),
                ('amount_due__gt', Decimal('0')),
            ],
        )

    def test_overdue_q_applies_prefix_to_shared_fields(self):
        if Case is None:
            self.skipTest('Django is not installed in the validation environment')

        overdue_filter = overdue_q(today=date(2026, 3, 24), prefix='invoice__')

        self.assert_q_children_equal(
            overdue_filter.children,
            [
                ('invoice__due_date__lt', date(2026, 3, 24)),
                ('invoice__amount_due__gt', Decimal('0')),
            ],
        )

    def test_overdue_boundary_annotation_applies_prefix_to_shared_boundary(self):
        if Case is None or BooleanField is None:
            self.skipTest('Django is not installed in the validation environment')

        annotation = overdue_boundary(today=date(2026, 3, 24)).annotation(prefix='invoice__')

        self.assertIsInstance(annotation, Case)
        self.assertIsInstance(annotation.output_field, BooleanField)
        when = annotation.cases[0]
        self.assert_q_children_equal(
            when.condition.children,
            [
                ('invoice__due_date__lt', date(2026, 3, 24)),
                ('invoice__amount_due__gt', Decimal('0')),
            ],
        )

    def test_overdue_read_paths_reuse_one_boundary_for_match_and_query(self):
        if Case is None:
            self.skipTest('Django is not installed in the validation environment')

        paths = overdue_read_paths(
            today=date(2026, 3, 25),
            prefix='invoice__',
            boundary=overdue_boundary(today=date(2026, 3, 24)),
        )

        self.assertTrue(
            paths.matches(
                due_date=date(2026, 3, 23),
                amount_due='10.00',
            )
        )
        self.assert_q_children_equal(
            paths.q().children,
            [
                ('invoice__due_date__lt', date(2026, 3, 24)),
                ('invoice__amount_due__gt', Decimal('0')),
            ],
        )

    def test_overdue_read_paths_matches_is_false_when_due_date_is_today(self):
        paths = overdue_read_paths(today=date(2026, 3, 24))

        self.assertFalse(
            paths.matches(
                due_date=date(2026, 3, 24),
                amount_due='10.00',
            )
        )

    def test_overdue_read_paths_matches_is_true_with_decimal_amount_due(self):
        paths = overdue_read_paths(today=date(2026, 3, 24))

        self.assertTrue(
            paths.matches(
                due_date=date(2026, 3, 23),
                amount_due=Decimal('10.00'),
            )
        )

    def test_overdue_read_paths_annotation_uses_shared_boundary(self):
        if overdue_annotation is None or Case is None or BooleanField is None:
            self.skipTest('Django is not installed in the validation environment')

        paths = overdue_read_paths(
            today=date(2026, 3, 25),
            boundary=overdue_boundary(today=date(2026, 3, 24)),
        )

        annotation = paths.annotation()

        self.assertIsInstance(annotation, Case)
        self.assertIsInstance(annotation.output_field, BooleanField)
        when = annotation.cases[0]
        self.assert_q_children_equal(
            when.condition.children,
            [
                ('due_date__lt', date(2026, 3, 24)),
                ('amount_due__gt', Decimal('0')),
            ],
        )

    def test_overdue_read_paths_annotation_applies_prefix_to_shared_fields(self):
        if overdue_annotation is None or Case is None or BooleanField is None:
            self.skipTest('Django is not installed in the validation environment')

        annotation = overdue_read_paths(
            today=date(2026, 3, 24),
            prefix='invoice__',
        ).annotation()

        when = annotation.cases[0]
        self.assert_q_children_equal(
            when.condition.children,
            [
                ('invoice__due_date__lt', date(2026, 3, 24)),
                ('invoice__amount_due__gt', Decimal('0')),
            ],
        )

    def test_overdue_annotation_is_boolean_case_expression(self):
        if overdue_annotation is None or Case is None or BooleanField is None:
            self.skipTest('Django is not installed in the validation environment')

        annotation = overdue_annotation(today=date(2026, 3, 24))

        self.assertIsInstance(annotation, Case)
        self.assertIsInstance(annotation.output_field, BooleanField)

    def test_overdue_annotation_uses_explicit_boundary_over_today_override(self):
        if overdue_annotation is None or Case is None or BooleanField is None:
            self.skipTest('Django is not installed in the validation environment')

        annotation = overdue_annotation(
            today=date(2026, 3, 25),
            boundary=overdue_boundary(today=date(2026, 3, 24)),
        )

        when = annotation.cases[0]
        self.assert_q_children_equal(
            when.condition.children,
            [
                ('due_date__lt', date(2026, 3, 24)),
                ('amount_due__gt', Decimal('0')),
            ],
        )

    def test_overdue_annotation_applies_prefix_to_shared_fields(self):
        if overdue_annotation is None or Case is None or BooleanField is None:
            self.skipTest('Django is not installed in the validation environment')

        annotation = overdue_annotation(today=date(2026, 3, 24), prefix='invoice__')

        when = annotation.cases[0]
        self.assert_q_children_equal(
            when.condition.children,
            [
                ('invoice__due_date__lt', date(2026, 3, 24)),
                ('invoice__amount_due__gt', Decimal('0')),
            ],
        )

    def test_annotate_is_overdue_adds_shared_annotation_name(self):
        if annotate_is_overdue is None or Invoice is None:
            self.skipTest('Django is not installed in the validation environment')

        queryset = annotate_is_overdue(Invoice.objects.all(), today=date(2026, 3, 24))

        self.assertIn(IS_OVERDUE_ANNOTATION, queryset.query.annotations)

    def test_annotate_is_overdue_supports_prefixed_custom_annotation_name(self):
        if annotate_is_overdue is None:
            self.skipTest('Django is not installed in the validation environment')

        class FakeQuerySet:
            def __init__(self):
                self.annotated_kwargs = {}

            def annotate(self, **kwargs):
                self.annotated_kwargs = kwargs
                return self

        queryset = FakeQuerySet()

        annotated = annotate_is_overdue(
            queryset,
            today=date(2026, 3, 24),
            prefix='invoice__',
            annotation_name='invoice_is_overdue',
        )

        self.assertIs(annotated, queryset)
        self.assertIn('invoice_is_overdue', queryset.annotated_kwargs)

        if Case is None or BooleanField is None:
            return

        annotation = queryset.annotated_kwargs['invoice_is_overdue']
        self.assertIsInstance(annotation, Case)
        self.assertIsInstance(annotation.output_field, BooleanField)
        when = annotation.cases[0]
        self.assert_q_children_equal(
            when.condition.children,
            [
                ('invoice__due_date__lt', date(2026, 3, 24)),
                ('invoice__amount_due__gt', Decimal('0')),
            ],
        )
