from django.contrib import admin
from django.urls import path, include
from allauth.account.views import login, signup, logout, password_reset, password_reset_done, password_reset_from_key

urlpatterns = [
    path("", include("core.urls")),
    path("admin/", admin.site.urls),
    
    # Rute scurte
    path("signin/", login, name="signin"),
    path("signup/", signup, name="signup"),
    path("logout/", logout, name="logout"),
    path("password-reset/", password_reset, name="password_reset"),
    path("password-reset/done/", password_reset_done, name="password_reset_done"),
    path("password-reset/confirm/<uidb36>/<key>/", password_reset_from_key, name="password_reset_from_key"),
    
    # Restul rutelor allauth ramân sub accounts/
    path("accounts/", include("allauth.urls")),
]