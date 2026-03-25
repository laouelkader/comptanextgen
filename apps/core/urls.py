from django.urls import path

from .views import AdminDashboardView, CustomLogoutView, DashboardView, LoginView

app_name = "core"

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("admin-dashboard/", AdminDashboardView.as_view(), name="admin_dashboard"),
    path("logout/", CustomLogoutView.as_view(), name="logout"),
]

