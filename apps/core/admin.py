from django.contrib import admin

from .models import AuditLog, Company, User


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("nom", "is_active", "created_at", "updated_at")
    search_fields = ("nom", "email")


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "role", "company", "is_active", "two_factor_enabled", "last_login")
    list_filter = ("role", "is_active", "two_factor_enabled")
    search_fields = ("email", "first_name", "last_name")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "model_name", "object_id", "timestamp", "ip_address", "company")
    list_filter = ("action", "model_name", "timestamp")
    search_fields = ("object_id", "ip_address", "model_name")

