from rest_framework.views import exception_handler


def json_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return response

    details = response.data
    detail = details.get('detail') if isinstance(details, dict) else details
    error = {
        'code': getattr(getattr(exc, 'default_code', None), 'value', None) or getattr(exc, 'default_code', 'error'),
        'message': str(detail) if detail is not None else 'Validation error.',
    }
    if detail is None and details:
        error['details'] = details
    response.data = {
        'error': {
            **error,
        }
    }
    return response
