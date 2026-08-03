from django.urls import path
from . import views

app_name = 'sales'

urlpatterns = [
    # Sales
    path('', views.sale_list, name='sale_list'),
    path('create/', views.sale_create, name='sale_create'),
    path('returns/', views.return_list, name='return_list'),
    path('returns/create/', views.return_create, name='return_create'),
    path('returns/<int:pk>/', views.return_detail, name='return_detail'),
    path('<int:pk>/', views.sale_detail, name='sale_detail'),
    path('<int:pk>/cancel/', views.sale_cancel, name='sale_cancel'),
    path('<int:pk>/payment/', views.sale_payment, name='sale_payment'),
    path('<int:pk>/print/', views.sale_print, name='sale_print'),
    
    # API
    path('api/products/search/', views.api_product_search, name='api_product_search'),
    path('api/pos_checkout/', views.pos_checkout, name='pos_checkout'),
]
