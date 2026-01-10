from django.urls import path
from . import views

urlpatterns = [
    # Warehouses
    path('', views.warehouse_list, name='warehouse_list'),
    path('create/', views.warehouse_create, name='warehouse_create'),
    path('<int:pk>/', views.warehouse_detail, name='warehouse_detail'),
    path('<int:pk>/edit/', views.warehouse_edit, name='warehouse_edit'),
    
    # Transfers
    path('transfers/', views.transfer_list, name='transfer_list'),
    path('transfers/create/', views.transfer_create, name='transfer_create'),
    path('transfers/<int:pk>/', views.transfer_detail, name='transfer_detail'),
    path('transfers/<int:pk>/complete/', views.transfer_complete, name='transfer_complete'),
    path('transfers/<int:pk>/cancel/', views.transfer_cancel, name='transfer_cancel'),
    
    # API
    path('api/<int:warehouse_id>/batches/', views.api_warehouse_batches, name='api_warehouse_batches'),
]
