import os


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')

try:
    import django
except ModuleNotFoundError:
    django = None

if django is not None:
    django.setup()
