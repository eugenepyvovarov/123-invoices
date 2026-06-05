from __future__ import annotations

import calendar
from datetime import date
from typing import Dict, List, Optional, Tuple


ROLLING_YEAR_DATE_RANGE_KEY = 'rolling_year'
DEFAULT_DATE_RANGE_KEY = ROLLING_YEAR_DATE_RANGE_KEY


def _month_bounds(reference: date) -> Tuple[date, date]:
    start = reference.replace(day=1)
    last_day = calendar.monthrange(reference.year, reference.month)[1]
    end = reference.replace(day=last_day)
    return start, end


def _previous_month(reference: date) -> date:
    first_of_month = reference.replace(day=1)
    previous_month_end = first_of_month - date.resolution
    return previous_month_end.replace(day=1)


def _subtract_months(reference: date, months: int) -> date:
    month_index = reference.year * 12 + reference.month - 1 - months
    year = month_index // 12
    month = month_index % 12 + 1
    return reference.replace(year=year, month=month)


def get_date_range_bounds(range_key: str, today: Optional[date] = None) -> Tuple[Optional[date], Optional[date]]:
    if today is None:
        today = date.today()

    if range_key == ROLLING_YEAR_DATE_RANGE_KEY:
        current_month_start = today.replace(day=1)
        start = _subtract_months(current_month_start, 12)
        _, end = _month_bounds(today)
        return start, end

    if range_key == 'all':
        return None, None

    if range_key == 'ytd':
        start = date(today.year, 1, 1)
        return start, today

    if range_key == 'last_year':
        start = date(today.year - 1, 1, 1)
        end = date(today.year - 1, 12, 31)
        return start, end

    if range_key == 'this_month':
        start, end = _month_bounds(today)
        return start, end

    if range_key == 'last_month':
        previous_month_start = _previous_month(today)
        start, end = _month_bounds(previous_month_start)
        return start, end

    return None, None


def _format_range_display(start: Optional[date], end: Optional[date]) -> str:
    if start and end:
        return f"{_format_date_display(start)} - {_format_date_display(end)}"
    if start and not end:
        return f"From {_format_date_display(start)}"
    if not start and end:
        return f"Up to {_format_date_display(end)}"
    return ''


def get_date_range_options(today: Optional[date] = None) -> List[Dict[str, str]]:
    if today is None:
        today = date.today()

    this_month_label = today.strftime("%b '%y")
    last_month_date = _previous_month(today)
    last_month_label = last_month_date.strftime("%b '%y")

    options = [
        {'value': ROLLING_YEAR_DATE_RANGE_KEY, 'label': 'Rolling Year'},
        {'value': 'this_month', 'label': f"This Month({this_month_label})"},
        {'value': 'last_month', 'label': f"Last Month({last_month_label})"},
        {'value': 'ytd', 'label': f"YTD({today.year})"},
        {'value': 'last_year', 'label': f"Last year({today.year - 1})"},
        {'value': 'all', 'label': 'All time'},
    ]

    for option in options:
        start, end = get_date_range_bounds(option['value'], today)
        option['range_display'] = _format_range_display(start, end)

    return options


def _format_date_display(value: Optional[date]) -> Optional[str]:
    if value is None:
        return None
    return value.strftime('%d %b %Y')


def _build_summary(label: str, start: Optional[date], end: Optional[date]) -> Dict[str, str]:
    if start and end:
        span = f"{_format_date_display(start)} - {_format_date_display(end)}"
        return {
            'summary': f"Showing data for {label} - {span}",
            'span': span,
        }
    if start and not end:
        span = f"From {_format_date_display(start)}"
        return {
            'summary': f"Showing data since {_format_date_display(start)}",
            'span': span,
        }
    if not start and end:
        span = f"Up to {_format_date_display(end)}"
        return {
            'summary': f"Showing data up to {_format_date_display(end)}",
            'span': span,
        }
    return {
        'summary': f"Showing data for {label}",
        'span': '',
    }


def get_global_date_filter(request) -> Dict[str, object]:
    if hasattr(request, '_global_date_filter'):
        return request._global_date_filter  # type: ignore[attr-defined]

    today = date.today()
    options = get_date_range_options(today)
    option_map = {opt['value']: opt['label'] for opt in options}
    valid_keys = set(option_map.keys())

    selected = request.GET.get('date_range')
    if selected in valid_keys:
        request.session['global_date_range'] = selected

    active_key = request.session.get('global_date_range', DEFAULT_DATE_RANGE_KEY)
    if active_key not in valid_keys:
        active_key = DEFAULT_DATE_RANGE_KEY

    start, end = get_date_range_bounds(active_key, today)
    label = option_map[active_key]
    summary_info = _build_summary(label, start, end)

    filter_context: Dict[str, object] = {
        'key': active_key,
        'label': label,
        'options': options,
        'start': start,
        'end': end,
        'summary': summary_info['summary'],
        'span': summary_info['span'],
        'range_display': summary_info['span'],
    }

    request._global_date_filter = filter_context  # type: ignore[attr-defined]
    return filter_context
