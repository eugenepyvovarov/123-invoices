from django.urls import path

from . import views


app_name = 'api'

urlpatterns = [
    path('invoices/', views.InvoiceCollectionView.as_view(), name='invoice-list'),
    path('invoices/<int:invoice_id>/', views.InvoiceDetailView.as_view(), name='invoice-detail'),
    path('invoices/<int:invoice_id>/finalize/', views.InvoiceFinalizeView.as_view(), name='invoice-finalize'),
    path('invoices/<int:invoice_id>/generate-pdf/', views.InvoiceGeneratePDFView.as_view(), name='invoice-generate-pdf'),
    path('invoices/<int:invoice_id>/pdf/', views.InvoicePDFView.as_view(), name='invoice-pdf'),
    path('issuers/', views.IssuerListView.as_view(), name='issuer-list'),
    path('customers/', views.CustomerListView.as_view(), name='customer-list'),
    path('projects/', views.ProjectListView.as_view(), name='project-list'),
    path('bank-accounts/', views.BankAccountListView.as_view(), name='bank-account-list'),
    path('invoice-line-suggestions/', views.InvoiceLineSuggestionListView.as_view(), name='invoice-line-suggestions'),
]
