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
    path('incoming/', views.incoming_inbox, name='incoming_inbox'),
    path('incoming/sources/', views.incoming_source_settings, name='incoming_sources'),
    path('incoming/routing/', views.incoming_routing_settings, name='incoming_routing'),
    path('incoming/<int:pk>/', views.incoming_candidate_detail, name='incoming_detail'),
    path('incoming/<int:pk>/action/', views.incoming_candidate_action, name='incoming_action'),
    path('incoming/<int:pk>/convert/', views.incoming_candidate_convert, name='incoming_convert'),
    path('incoming/<int:pk>/artifacts/<int:artifact_id>/download/', views.incoming_artifact_download, name='incoming_artifact_download'),
    path('incoming/<int:pk>/artifacts/<int:artifact_id>/preview/', views.incoming_artifact_preview, name='incoming_artifact_preview'),
    path('<int:pk>/delete/', views.expense_delete, name='delete'),
]
