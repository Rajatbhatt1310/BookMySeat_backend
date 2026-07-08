"""
WSGI config for bookmyseat project.

It exposes the WSGI callable as a module-level variable named ``application``.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bookmyseat.settings")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
app = application



from django.contrib.auth import get_user_model

User = get_user_model()

USERNAME = "admin"
PASSWORD = "Admin@12345"
EMAIL = "rajatbhatt1310@gmail.com"   

user, created = User.objects.get_or_create(
    username=USERNAME,
    defaults={
        "email": EMAIL,
        "is_staff": True,
        "is_superuser": True,
    },
)

user.set_password(PASSWORD)
user.is_staff = True
user.is_superuser = True
user.save()

print("✓ Admin user created/updated successfully")
