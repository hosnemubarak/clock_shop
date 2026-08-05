from django.urls import path
from . import views

app_name = 'customers'

urlpatterns = [
    # Customers
    path('', views.customer_list, name='customer_list'),
    path('create/', views.customer_create, name='customer_create'),
    path('<int:pk>/', views.customer_detail, name='customer_detail'),
    path('<int:pk>/edit/', views.customer_edit, name='customer_edit'),
    path('<int:pk>/add-note/', views.customer_add_note, name='customer_add_note'),
    path('<int:pk>/statement/', views.customer_statement, name='customer_statement'),
    
    # Payments
    path('payments/', views.payment_list, name='payment_list'),
    path('payments/create/', views.payment_create, name='payment_create'),
    path('payments/<int:pk>/print/', views.payment_print, name='payment_print'),
    
    # API
    path('api/create/', views.api_customer_create, name='api_customer_create'),
    path('api/search/', views.api_customer_search, name='api_customer_search'),
    path('api/<int:customer_id>/', views.api_customer_info, name='api_customer_info'),
    path('api/<int:customer_id>/sales/', views.api_customer_sales, name='api_customer_sales'),
]
