from django.urls import path
from . import views

app_name = 'quotations'

urlpatterns = [
    path('', views.quotation_list, name='quotation_list'),
    path('create/', views.quotation_create, name='quotation_create'),
    path('<int:pk>/', views.quotation_detail, name='quotation_detail'),
    path('<int:pk>/print/', views.quotation_print, name='quotation_print'),
    path('<int:pk>/delete/', views.quotation_delete, name='quotation_delete'),

    # API
    path('api/save/', views.api_quotation_save, name='api_quotation_save'),
    path('api/products/search/', views.api_product_search, name='api_product_search'),
]
