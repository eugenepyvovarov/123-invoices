from django.urls import path

from . import views

app_name = 'expenses'

urlpatterns = [
    path('', views.expense_index, name='list'),
    path('drawer/', views.expense_drawer, name='drawer_new'),
    path('<int:pk>/drawer/', views.expense_drawer, name='drawer'),
    path('<int:pk>/reporting-visibility/', views.expense_reporting_visibility, name='reporting_visibility'),
    path('bulk/download/', views.expense_bulk_download, name='bulk_download'),
    path('import/', views.expense_csv_import, name='csv_import'),
    path('import/<int:batch_id>/review/', views.expense_csv_import_review, name='csv_import_review'),
    path('import/<int:batch_id>/confirm/', views.expense_csv_import_confirm, name='csv_import_confirm'),
    path('<int:pk>/delete/', views.expense_delete, name='delete'),
]
