from django.urls import path

from .views import AlertsView, AnalyticsView, ReportingExcelExportView

app_name = "reporting"

urlpatterns = [
    path("analytics/", AnalyticsView.as_view(), name="analytics"),
    path("alerts/", AlertsView.as_view(), name="alerts"),
    path("export/excel/", ReportingExcelExportView.as_view(), name="export_excel"),
]

