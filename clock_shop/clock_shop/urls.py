"""
URL configuration for clock_shop project.
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.core.urls')),
    path('inventory/', include('apps.inventory.urls')),
    path('sales/', include('apps.sales.urls')),
    path('customers/', include('apps.customers.urls')),
    path('warehouse/', include('apps.warehouse.urls')),
    path('reports/', include('apps.reports.urls')),
]

# Serve media files in both development and production
# In production with high traffic, consider using a reverse proxy (nginx) instead
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
