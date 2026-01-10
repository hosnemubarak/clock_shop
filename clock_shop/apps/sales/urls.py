from django.urls import path
from . import views

urlpatterns = [
    # Sales
    path('', views.sale_list, name='sale_list'),
    path('create/', views.sale_create, name='sale_create'),
    path('<int:pk>/', views.sale_detail, name='sale_detail'),
    path('<int:pk>/cancel/', views.sale_cancel, name='sale_cancel'),
    path('<int:pk>/payment/', views.sale_payment, name='sale_payment'),
    path('<int:pk>/print/', views.sale_print, name='sale_print'),
    
    # POS
    path('pos/', views.pos_view, name='pos'),
    
    # API
    path('api/products/<int:product_id>/', views.api_product_info, name='api_product_info'),
]
