from django.contrib.auth.decorators import user_passes_test

def is_admin(user):
    return user.is_active and (user.is_superuser or user.groups.filter(name='Admin').exists())

def is_manager(user):
    return user.is_active and (is_admin(user) or user.groups.filter(name='Manager').exists())

def is_cashier(user):
    return user.is_active and (is_manager(user) or user.groups.filter(name='Cashier').exists())

admin_required = user_passes_test(is_admin, login_url='/login/')
manager_required = user_passes_test(is_manager, login_url='/login/')
cashier_required = user_passes_test(is_cashier, login_url='/login/')
