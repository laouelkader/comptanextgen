from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from apps.treasury.views import simulated_bank_transactions_api


urlpatterns = [
    path("admin/", admin.site.urls),

    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
    path("", include("apps.core.urls")),
    path("accounting/", include("apps.accounting.urls")),
    path("invoicing/", include("apps.invoicing.urls")),
    path("treasury/", include("apps.treasury.urls")),
    path("reporting/", include("apps.reporting.urls")),

    # API banque simulée (spécification)
    path("api/bank-simulator/<int:company_id>/", simulated_bank_transactions_api, name="bank_simulator_api"),
]

