from django.urls import path

from .views import (
    EntryCreateView,
    EntryListView,
    EntryValidateView,
    FinancialStatementsExcelView,
    FinancialStatementsPDFView,
    FinancialStatementsView,
)

app_name = "accounting"

urlpatterns = [
    path("entries/", EntryListView.as_view(), name="entry_list"),
    path("entries/add/", EntryCreateView.as_view(), name="entry_add"),
    path("entries/<int:pk>/validate/", EntryValidateView.as_view(), name="entry_validate"),
    path("statements/", FinancialStatementsView.as_view(), name="statements"),
    path("statements/export/excel/", FinancialStatementsExcelView.as_view(), name="statements_excel"),
    path("statements/export/pdf/", FinancialStatementsPDFView.as_view(), name="statements_pdf"),
]

