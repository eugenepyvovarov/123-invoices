from invoices.models import Customer
from invoices.utils.company_context import get_active_issuer, get_available_issuers
from invoices.utils.date_filters import get_global_date_filter


def active_company(request):
    issuer = get_active_issuer(request)
    issuers = get_available_issuers(request)
    active_customers = []
    if issuer:
        active_customers = list(
            Customer.objects.filter(
                issuer=issuer,
                is_active=True,
                company__isnull=False,
            )
            .select_related('company')
            .order_by('company__name')
        )

    return {
        'active_issuer': issuer,
        'issuer_companies': [
            issuer_instance for issuer_instance in issuers if issuer_instance.company
        ],
        'sidebar_active_customers': active_customers,
    }


def global_date_filter(request):
    filter_context = get_global_date_filter(request)
    return {
        'global_date_filter': filter_context,
    }
