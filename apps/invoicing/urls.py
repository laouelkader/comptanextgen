from django.urls import path

from .views import (
    InvoiceCreateView,
    InvoiceExcelExportView,
    InvoiceListView,
    InvoicePDFView,
    QuoteConvertView,
    QuoteCreateView,
    QuoteListView,
)

app_name = "invoicing"

urlpatterns = [
    path("quotes/", QuoteListView.as_view(), name="quote_list"),
    path("quotes/add/", QuoteCreateView.as_view(), name="quote_add"),
    path("quotes/<int:quote_id>/convert/", QuoteConvertView.as_view(), name="quote_convert"),

    path("invoices/", InvoiceListView.as_view(), name="invoice_list"),
    path("invoices/add/", InvoiceCreateView.as_view(), name="invoice_add"),
    path("invoices/export/excel/", InvoiceExcelExportView.as_view(), name="invoice_export_excel"),
    path("invoices/<int:invoice_id>/pdf/", InvoicePDFView.as_view(), name="invoice_pdf"),
]

