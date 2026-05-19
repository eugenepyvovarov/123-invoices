from django import template


register = template.Library()


@register.filter
def get_item(value, key):
    if isinstance(value, dict):
        return value.get(key, '')
    return ''


@register.filter
def mapping_column_selected(value, header):
    if isinstance(value, (list, tuple, set)):
        return header in value
    return value == header


def _apply_cell_labels(order_columns, rows):
    labels = []
    for column in order_columns or []:
        if isinstance(column, dict):
            labels.append(column.get('label', '') or '')
        else:
            labels.append('')

    annotated_rows = []
    for row in rows or []:
        if not isinstance(row, dict):
            annotated_rows.append(row)
            continue

        cells = row.get('cells') or []
        annotated_cells = []
        for idx, cell in enumerate(cells):
            if isinstance(cell, dict):
                annotated_cell = dict(cell)
            else:
                annotated_cell = {'content': cell}

            label = labels[idx] if idx < len(labels) else ''
            if label and not annotated_cell.get('colspan'):
                annotated_cell['label'] = label

            annotated_cells.append(annotated_cell)

        annotated_row = dict(row)
        annotated_row['cells'] = annotated_cells
        annotated_rows.append(annotated_row)

    return annotated_rows



@register.inclusion_tag('invoices/partials/data_table.html')
def render_data_table(order_columns, rows, query_without_order='', footer=None, empty_message=None):
    resolved_rows = _apply_cell_labels(order_columns, rows)
    resolved_footer = None
    if isinstance(footer, dict):
        resolved_footer_cells = _apply_cell_labels(order_columns, [footer])
        if resolved_footer_cells:
            resolved_footer = resolved_footer_cells[0]
    return {
        'order_columns': order_columns or [],
        'rows': resolved_rows,
        'query_without_order': query_without_order or '',
        'footer_row': resolved_footer,
        'empty_message': empty_message or 'No records to display.',
    }
