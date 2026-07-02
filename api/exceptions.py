from rest_framework.views import exception_handler


def json_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return response

    detail = response.data.get('detail') if isinstance(response.data, dict) else response.data
    response.data = {
        'error': {
            'code': getattr(getattr(exc, 'default_code', None), 'value', None) or getattr(exc, 'default_code', 'error'),
            'message': str(detail),
        }
    }
    return response
