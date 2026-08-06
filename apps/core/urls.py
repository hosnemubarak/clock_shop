from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', auth_views.LoginView.as_view(template_name='core/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('register/', views.register, name='register'),
    path('audit-logs/', views.audit_logs, name='audit_logs'),
    path('settings/', views.system_settings, name='system_settings'),
    path('unauthorized/', views.unauthorized, name='unauthorized'),
    path('staff/', views.staff_list, name='staff_list'),
    path('staff/<int:pk>/update-role/', views.update_staff_role, name='update_staff_role'),
    path('staff/<int:pk>/update-password/', views.update_staff_password, name='update_staff_password'),
    path('staff/<int:pk>/delete/', views.delete_staff, name='delete_staff'),
    path('profile/', views.profile_update, name='profile_update'),
    path('password/', views.CustomPasswordChangeView.as_view(), name='password_change'),
]
