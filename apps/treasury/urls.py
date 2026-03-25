from django.urls import path

from .views import CashForecastView, BankReconciliationView, TreasuryDashboardView

app_name = "treasury"

urlpatterns = [
    path("dashboard/", TreasuryDashboardView.as_view(), name="treasury_dashboard"),
    path("reconciliation/", BankReconciliationView.as_view(), name="reconciliation"),
    path("forecast/", CashForecastView.as_view(), name="forecast"),
]

