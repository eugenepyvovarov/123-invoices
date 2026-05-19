from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from . import views

customer_urlpatterns = [
    path('', views.view_customers, name='list'),
    path('add/', views.add_customer, name='add'),
    path('<int:id>/', views.customer_profile, name='detail'),
    path('<int:id>/edit/', views.make_customer, name='edit'),
    path('<int:id>/delete/', views.delete_customer, name='delete'),
    path('<int:id>/payments/add/', views.customer_add_payment, name='add_payment'),
]

invoice_urlpatterns = [
    path('', views.view_invoices, name='list'),
    path('add/', views.add_invoice, name='add'),
    path('bulk/last-month/', views.bulk_last_month, name='bulk_last_month'),
    path('bulk/action/', views.invoice_bulk_action, name='bulk_action'),
    path('export/all-pdf/', views.save_all_invoices_pdf, name='export_all_pdf'),
    path('<int:id>/', views.make_invoice, name='edit'),
    path('<int:id>/drawer/', views.invoice_drawer, name='drawer'),
    path('<int:id>/autosave/', views.invoice_autosave, name='autosave'),
    path('<int:id>/quick-save/', views.invoice_quick_save, name='quick_save'),
    path('<int:id>/status/', views.invoice_status_update, name='status'),
    path('<int:id>/pdf/', views.check_pdf, name='pdf'),
    path('<int:id>/generate-pdf/', views.invoice_generate_pdf, name='generate_pdf'),
    path('<int:id>/payments/add/', views.invoice_add_payment, name='add_payment'),
    path(
        '<int:id>/payments/applications/<int:application_id>/remove/',
        views.invoice_remove_payment_application,
        name='remove_payment_application',
    ),
    path('payments/import-wise/', views.payments_import_wise, name='payments_import_wise'),
    path('payments/<int:id>/prefill/', views.payment_prefill, name='payment_prefill'),
    path('payments/<int:id>/delete/', views.payment_delete, name='payment_delete'),
    path('<int:id>/delete/', views.delete_invoice, name='delete'),
]

project_urlpatterns = [
    path('', views.view_projects, name='list'),
    path('add/', views.add_project, name='add'),
    path('<int:id>/', views.project_detail, name='detail'),
    path('<int:id>/edit/', views.edit_project, name='edit'),
    path('<int:id>/recent-items/', views.project_recent_items, name='recent_items'),
    path('<int:id>/outstanding-invoices/', views.project_outstanding_invoices, name='outstanding_invoices'),
]

company_urlpatterns = [
    path('', views.edit_company, name='settings'),
    path('switch/', views.switch_company, name='switch'),
]

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('dashboard/', views.dashboard),
    path('dashboard/cross-company/', views.cross_company_dashboard, name='cross_company_dashboard'),
    path('dashboard/cross-company/open/', views.cross_company_switch_redirect, name='cross_company_switch_redirect'),
    path('backup-settings/', views.backup_settings, name='backup_settings'),
    path('backup-settings/runs/<int:id>/', views.backup_run_detail, name='backup_run_detail'),
    path('backup-settings/runs/<int:id>/download/', views.backup_run_download, name='backup_run_download'),
    path('backup-settings/run-now/', views.run_backup_now, name='backup_run_now'),
    path('customers/', include((customer_urlpatterns, 'customers'), namespace='customers')),
    path('invoices/', include((invoice_urlpatterns, 'invoices'), namespace='invoices')),
    path('projects/', include((project_urlpatterns, 'projects'), namespace='projects')),
    path('company/', include((company_urlpatterns, 'company'), namespace='company')),
    path('expenses/', include(('expenses.urls', 'expenses'), namespace='expenses')),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
