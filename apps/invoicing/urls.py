from django.urls import path

from .views import (
    InvoiceCancelView,
    InvoiceCreateView,
    InvoiceEditView,
    InvoiceExcelExportView,
    InvoiceHistoryView,
    InvoiceListView,
    InvoicePDFView,
    QuoteCancelView,
    QuoteConvertView,
    QuoteCreateView,
    QuoteEditView,
    QuoteHistoryView,
    QuoteListView,
)

app_name = "invoicing"

urlpatterns = [
    path("quotes/", QuoteListView.as_view(), name="quote_list"),
    path("quotes/add/", QuoteCreateView.as_view(), name="quote_add"),
    path("quotes/<int:quote_id>/edit/", QuoteEditView.as_view(), name="quote_edit"),
    path("quotes/<int:quote_id>/cancel/", QuoteCancelView.as_view(), name="quote_cancel"),
    path("quotes/<int:quote_id>/history/", QuoteHistoryView.as_view(), name="quote_history"),
    path("quotes/<int:quote_id>/convert/", QuoteConvertView.as_view(), name="quote_convert"),

    path("invoices/", InvoiceListView.as_view(), name="invoice_list"),
    path("invoices/add/", InvoiceCreateView.as_view(), name="invoice_add"),
    path("invoices/<int:invoice_id>/edit/", InvoiceEditView.as_view(), name="invoice_edit"),
    path("invoices/<int:invoice_id>/cancel/", InvoiceCancelView.as_view(), name="invoice_cancel"),
    path("invoices/<int:invoice_id>/history/", InvoiceHistoryView.as_view(), name="invoice_history"),
    path("invoices/export/excel/", InvoiceExcelExportView.as_view(), name="invoice_export_excel"),
    path("invoices/<int:invoice_id>/pdf/", InvoicePDFView.as_view(), name="invoice_pdf"),
]

