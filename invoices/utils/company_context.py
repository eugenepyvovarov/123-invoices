from __future__ import annotations

from typing import Optional

from django.http import HttpRequest

from invoices.models import Issuer


def _issuer_queryset_for_request(request: HttpRequest):
    issuers = Issuer.objects.select_related('company').order_by('company__name')
    user = getattr(request, 'user', None)
    if user and user.is_authenticated and not user.is_superuser:
        issuers = issuers.filter(users=user)
    return issuers


def get_available_issuers(request: HttpRequest):
    """Return issuers available to the current request/user."""
    return _issuer_queryset_for_request(request)


def get_active_issuer(request: HttpRequest) -> Optional[Issuer]:
    """Return the issuer selected in the user session, defaulting to the first available."""

    company_id = request.session.get('active_company_id')

    issuers = _issuer_queryset_for_request(request)

    issuer = None
    if company_id:
        issuer = issuers.filter(company_id=company_id).first()

    if issuer is None:
        user = getattr(request, 'user', None)
        profile = getattr(user, 'profile', None) if user and user.is_authenticated else None
        default_company_id = getattr(profile, 'default_company_id', None)
        if default_company_id:
            issuer = issuers.filter(company_id=default_company_id).first()
            if issuer:
                request.session['active_company_id'] = issuer.company_id

    if issuer is None:
        issuer = issuers.first()
        if issuer:
            request.session['active_company_id'] = issuer.company_id

    return issuer


def set_active_company(request: HttpRequest, company_id: int) -> bool:
    """Persist the selected company in the session if it belongs to an issuer."""

    issuers = _issuer_queryset_for_request(request)
    exists = issuers.filter(company_id=company_id).exists()
    if exists:
        request.session['active_company_id'] = company_id
        return True
    return False
