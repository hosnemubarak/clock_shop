"""
Temporary Django View to Create Admin User
Add this to your urls.py temporarily, visit the URL once, then remove it.

SECURITY WARNING: This is for initial setup only. Remove after use!
"""

from django.http import HttpResponse
from django.contrib.auth import get_user_model
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def create_admin_user(request):
    """
    Temporary view to create admin user.
    Visit this URL once to create the admin, then REMOVE this view!
    """
    User = get_user_model()
    
    # Admin credentials - CHANGE THESE BEFORE USING!
    ADMIN_USERNAME = 'admin'
    ADMIN_EMAIL = 'admin@example.com'
    ADMIN_PASSWORD = 'ChangeThisPassword123!'  # IMPORTANT: Change this!
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Create Admin User</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }
            .success { color: green; }
            .error { color: red; }
            .warning { color: orange; background: #fff3cd; padding: 10px; border-left: 4px solid orange; }
            pre { background: #f4f4f4; padding: 10px; border-radius: 4px; }
        </style>
    </head>
    <body>
        <h1>Create Admin User</h1>
    """
    
    if User.objects.filter(username=ADMIN_USERNAME).exists():
        html += f"""
        <p class="error">✗ User '{ADMIN_USERNAME}' already exists!</p>
        <p>If you need to reset the password, use Django admin or database.</p>
        """
    else:
        try:
            user = User.objects.create_superuser(
                username=ADMIN_USERNAME,
                email=ADMIN_EMAIL,
                password=ADMIN_PASSWORD
            )
            html += f"""
            <p class="success">✓ Superuser created successfully!</p>
            <pre>
Username: {ADMIN_USERNAME}
Email: {ADMIN_EMAIL}
Password: {ADMIN_PASSWORD}
            </pre>
            <div class="warning">
                <strong>⚠ IMPORTANT SECURITY STEPS:</strong>
                <ol>
                    <li>Login to admin panel: <a href="/admin">/admin</a></li>
                    <li>Change your password immediately</li>
                    <li>Remove this view from urls.py</li>
                    <li>Delete create_admin_view.py file</li>
                    <li>Restart your application</li>
                </ol>
            </div>
            """
        except Exception as e:
            html += f"""
            <p class="error">✗ Error creating superuser: {e}</p>
            """
    
    html += """
    </body>
    </html>
    """
    
    return HttpResponse(html)


# Instructions to add to urls.py:
"""
TEMPORARY - Add this to your clock_shop/urls.py:

from create_admin_view import create_admin_user

urlpatterns = [
    # ... existing patterns ...
    path('create-admin-temp/', create_admin_user),  # REMOVE AFTER USE!
]

Then visit: https://yourdomain.com/create-admin-temp/
After creating admin, REMOVE this line and delete create_admin_view.py
"""
