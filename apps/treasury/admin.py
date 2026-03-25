from django.contrib import admin

from .models import BankAccount, BankTransaction, CashForecastItem


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ("company", "name", "bank_name", "initial_balance", "current_balance", "is_main")
    list_filter = ("is_main",)
    search_fields = ("name", "bank_name")


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ("bank_account", "date", "transaction_type", "amount", "reconciled", "import_id")
    list_filter = ("transaction_type", "reconciled", "date")
    search_fields = ("description", "import_id")


@admin.register(CashForecastItem)
class CashForecastItemAdmin(admin.ModelAdmin):
    list_display = ("company", "date", "description", "type", "amount", "is_recurring", "category", "is_actual")
    list_filter = ("type", "is_recurring", "is_actual", "category")
    search_fields = ("description", "category")

