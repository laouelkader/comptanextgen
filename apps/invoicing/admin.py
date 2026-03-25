from django.contrib import admin

from .models import Invoice, InvoiceLine, Quote


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = ("company", "number", "date", "valid_until", "status", "total_ht", "total_ttc", "created_at")
    list_filter = ("status", "date")
    search_fields = ("number", "client_name")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("company", "number", "date", "due_date", "status", "total_ht", "total_ttc", "reminder_count")
    list_filter = ("status", "date")
    search_fields = ("number", "client_name")


@admin.register(InvoiceLine)
class InvoiceLineAdmin(admin.ModelAdmin):
    list_display = ("invoice", "quote", "description", "quantity", "unit_price", "tax_rate", "amount_ht", "amount_ttc")
    search_fields = ("description",)

