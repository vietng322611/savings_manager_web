from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator
from .managers import CustomUserManager

class CustomUser(AbstractUser):
    """
    Custom user model for saving_manager_web.
    Using email as the primary identifier instead of username.
    """
    username = None
    email = models.EmailField(_('email address'), unique=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    @property
    def is_customer(self):
        return hasattr(self, "customer")

    @property
    def is_employee(self):
        return hasattr(self, "employee")

    def __str__(self):
        return self.email

class Customer(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="customer")

    full_name = models.CharField(max_length=50, default="")
    citizen_id = models.CharField(
        max_length=12,
        unique=True,
        validators=[
            RegexValidator(
                regex=r'^\d{12}$',
                message='Citizen ID must contain exactly 12 digits.'
            )
        ]
    )
    address = models.CharField(max_length=100, default="")

class EmployeeRole(models.TextChoices):
    READ = "READ", "Read Only"
    WRITE = "WRITE", "Read & Write"

class Employee(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="employee")
    role = models.CharField(max_length=30, choices=EmployeeRole)

    @property
    def can_edit(self):
        return self.role == EmployeeRole.WRITE