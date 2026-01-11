from django.urls import path
from . import views

urlpatterns = [
    # Products
    path('products/', views.product_list, name='product_list'),
    path('products/create/', views.product_create, name='product_create'),
    path('products/<int:pk>/', views.product_detail, name='product_detail'),
    path('products/<int:pk>/edit/', views.product_edit, name='product_edit'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),
    
    # Categories
    path('categories/', views.category_list, name='category_list'),
    path('categories/create/', views.category_create, name='category_create'),
    path('categories/<int:pk>/edit/', views.category_edit, name='category_edit'),
    
    # Brands
    path('brands/', views.brand_list, name='brand_list'),
    path('brands/create/', views.brand_create, name='brand_create'),
    path('brands/<int:pk>/edit/', views.brand_edit, name='brand_edit'),
    
    # Batches
    path('batches/', views.batch_list, name='batch_list'),
    path('batches/create/', views.batch_create, name='batch_create'),
    path('batches/<int:pk>/', views.batch_detail, name='batch_detail'),
    
    # Purchases
    path('purchases/', views.purchase_list, name='purchase_list'),
    path('purchases/create/', views.purchase_create, name='purchase_create'),
    path('purchases/<int:pk>/', views.purchase_detail, name='purchase_detail'),
    
    # Stock Out
    path('stockout/', views.stockout_list, name='stockout_list'),
    path('stockout/create/', views.stockout_create, name='stockout_create'),
    path('stockout/<int:pk>/', views.stockout_detail, name='stockout_detail'),
    path('stockout/<int:pk>/cancel/', views.stockout_cancel, name='stockout_cancel'),
    
    # API
    path('api/products/<int:product_id>/batches/', views.api_product_batches, name='api_product_batches'),
    path('api/warehouses/<int:warehouse_id>/batches/', views.api_warehouse_batches, name='api_warehouse_batches'),
]
