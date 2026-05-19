from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from django.db.models import QuerySet


ZERO = Decimal('0')
IS_OVERDUE_ANNOTATION = 'is_overdue'


def coerce_amount_due(value) -> Decimal:
    if value in (None, ''):
        return ZERO
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ZERO


def overdue_boundary_date(*, today: date | None = None) -> date:
    if today is not None:
        return today
    try:
        from django.utils import timezone

        return timezone.localdate()
    except ModuleNotFoundError:
        return date.today()


@dataclass(frozen=True)
class OverdueBoundary:
    today: date

    def due_date_lookup(self, *, prefix: str = '') -> tuple[str, date]:
        return (f'{prefix}due_date__lt', self.today)

    def is_past_due(self, due_date) -> bool:
        return bool(due_date and due_date < self.today)

    def q(self, *, prefix: str = ''):
        from django.db.models import Q

        due_date_field, due_date_cutoff = self.due_date_lookup(prefix=prefix)
        return Q(**{
            due_date_field: due_date_cutoff,
            f'{prefix}amount_due__gt': ZERO,
        })

    def matches(self, *, due_date, amount_due) -> bool:
        return bool(self.is_past_due(due_date) and coerce_amount_due(amount_due) > ZERO)

    def annotation(self, *, prefix: str = ''):
        from django.db.models import BooleanField, Case, Value, When

        return Case(
            When(self.q(prefix=prefix), then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        )


@dataclass(frozen=True)
class OverdueReadPaths:
    boundary: OverdueBoundary
    prefix: str = ''

    def q(self):
        return self.boundary.q(prefix=self.prefix)

    def matches(self, *, due_date, amount_due) -> bool:
        return self.boundary.matches(due_date=due_date, amount_due=amount_due)

    def annotation(self):
        return self.boundary.annotation(prefix=self.prefix)


def overdue_boundary(*, today: date | None = None) -> OverdueBoundary:
    return OverdueBoundary(today=overdue_boundary_date(today=today))


def resolve_overdue_boundary(*, boundary: OverdueBoundary | None = None, today: date | None = None) -> OverdueBoundary:
    if boundary is not None:
        return boundary
    return overdue_boundary(today=today)


def overdue_read_paths(
    *,
    today: date | None = None,
    prefix: str = '',
    boundary: OverdueBoundary | None = None,
) -> OverdueReadPaths:
    return OverdueReadPaths(
        boundary=resolve_overdue_boundary(boundary=boundary, today=today),
        prefix=prefix,
    )


def overdue_q(*, today: date | None = None, prefix: str = '', boundary: OverdueBoundary | None = None):
    return overdue_read_paths(today=today, prefix=prefix, boundary=boundary).q()


def is_invoice_overdue(*, due_date, amount_due, today: date | None = None, boundary: OverdueBoundary | None = None) -> bool:
    return overdue_read_paths(today=today, boundary=boundary).matches(due_date=due_date, amount_due=amount_due)


def overdue_annotation(*, today: date | None = None, prefix: str = '', boundary: OverdueBoundary | None = None):
    return overdue_read_paths(today=today, prefix=prefix, boundary=boundary).annotation()


def annotate_is_overdue(
    queryset: 'QuerySet',
    *,
    today: date | None = None,
    prefix: str = '',
    annotation_name: str = IS_OVERDUE_ANNOTATION,
    boundary: OverdueBoundary | None = None,
) -> Any:
    return queryset.annotate(**{
        annotation_name: overdue_annotation(today=today, prefix=prefix, boundary=boundary),
    })
