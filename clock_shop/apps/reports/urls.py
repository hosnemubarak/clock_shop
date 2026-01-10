from django.urls import path
from . import views

urlpatterns = [
    path('', views.report_dashboard, name='report_dashboard'),
    path('sales/', views.sales_report, name='sales_report'),
    path('profit/', views.profit_report, name='profit_report'),
    path('stock/', views.stock_report, name='stock_report'),
    path('customers/', views.customer_report, name='customer_report'),
    path('transfers/', views.transfer_report, name='transfer_report'),
    path('dead-stock/', views.dead_stock_report, name='dead_stock_report'),
    path('batches/', views.batch_report, name='batch_report'),
]
