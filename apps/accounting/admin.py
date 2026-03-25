from django.contrib import admin

from .models import AccountingEntry, ChartOfAccount, EntryLine


@admin.register(ChartOfAccount)
class ChartOfAccountAdmin(admin.ModelAdmin):
    list_display = ("account_number", "name", "type", "is_active")
    search_fields = ("account_number", "name")
    list_filter = ("type", "is_active")


class EntryLineInline(admin.TabularInline):
    model = EntryLine
    extra = 0
    readonly_fields = ("debit", "credit", "account")


@admin.register(AccountingEntry)
class AccountingEntryAdmin(admin.ModelAdmin):
    list_display = ("company", "date", "reference", "validated", "created_by", "created_at")
    list_filter = ("validated", "date")
    search_fields = ("reference", "description")
    inlines = [EntryLineInline]


@admin.register(EntryLine)
class EntryLineAdmin(admin.ModelAdmin):
    list_display = ("entry", "account", "debit", "credit")
    list_filter = ("account",)

