from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('test-telegram/', views.test_telegram, name='test_telegram'),
]
