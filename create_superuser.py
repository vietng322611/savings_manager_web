import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dashboard.settings")
django.setup()

from django.contrib.auth import get_user_model
from allauth.account.models import EmailAddress
from users.models import Employee, EmployeeRole

User = get_user_model()

email = os.getenv("DJANGO_SUPERUSER_EMAIL")
password = os.getenv("DJANGO_SUPERUSER_PASSWORD")

if not User.objects.filter(email=email).exists():
    user = User.objects.create_superuser(
        email=email,
        password=password
    )

    EmailAddress.objects.create(
        user=user,
        email=user.email,
        primary=True,
        verified=True
    )

    Employee.objects.create(
        user=user,
        role=EmployeeRole.WRITE
    )

    print("Superuser created")
else:
    print("Superuser already exists")