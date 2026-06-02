from allauth.account.models import EmailAddress
from django import forms
from django.db import transaction

from users.models import EmployeeRole, Employee, CustomUser, Customer
from savings.models import SavingType, SavingPlan


class EmployeeChangeForm(forms.Form):
    hasRead = forms.BooleanField(required=False)
    hasWrite = forms.BooleanField(required=False)

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

        if self.user.is_employee:
            self.fields["hasRead"].initial = True
            self.fields["hasWrite"].initial = user.employee.role == EmployeeRole.WRITE

    def clean(self):
        cleaned_data = super().clean()

        has_write = cleaned_data.get("hasWrite")
        if has_write:
            cleaned_data["hasRead"] = True

        return cleaned_data

    def save(self):
        has_read = self.cleaned_data["hasRead"]
        has_write = self.cleaned_data["hasWrite"]

        if has_write:
            role = EmployeeRole.WRITE
        else:
            role = EmployeeRole.READ

        with transaction.atomic():
            if not has_read:
                if self.user.is_employee:
                    self.user.employee.delete()
                return None

            employee, created = Employee.objects.get_or_create(user=self.user, defaults={"role": role})
            if employee.role != role:
                employee.role = role
                employee.save(update_fields=["role"])

            return employee

class UserCreateForm(forms.Form):
    email = forms.EmailField()
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    is_customer = forms.BooleanField(required=False)
    has_read = forms.BooleanField(required=False, initial=True)
    has_write = forms.BooleanField(required=False)

    full_name = forms.CharField(required=False)
    citizen_id = forms.CharField(required=False)
    address = forms.CharField(required=False)

    def clean(self):
        cleaned_data = super().clean()

        is_customer = cleaned_data.get("is_customer")
        has_write = cleaned_data.get("has_write")

        if has_write:
            cleaned_data["has_read"] = True

        if is_customer:
            required_fields = [
                "full_name",
                "citizen_id",
                "address"
            ]

            for field in required_fields:
                if not cleaned_data.get(field):
                    self.add_error(field, "This field is required.")

        return cleaned_data

    def save(self):
        with transaction.atomic():
            user = CustomUser.objects.create_user(
                email=self.cleaned_data["email"],
                password=self.cleaned_data["password1"]
            )

            EmailAddress.objects.create(
                user=user,
                email=user.email,
                verified=True,
                primary=True
            )

            if self.cleaned_data.get("has_read"):
                role = EmployeeRole.READ

                if self.cleaned_data.get("has_write"):
                    role = EmployeeRole.WRITE

                Employee.objects.create(
                    user=user,
                    role=role
                )

            if self.cleaned_data.get("is_customer"):
                Customer.objects.create(
                    user=user,
                    full_name=self.cleaned_data["full_name"],
                    citizen_id=self.cleaned_data["citizen_id"],
                    address=self.cleaned_data["address"]
                )

            return user

class SavingTypeEditForm(forms.ModelForm):
    class Meta:
        model = SavingType
        fields = ['name', 'duration_months', 'interest_rate', 'is_flexible', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Saving Type Name'}),
            'duration_months': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '3, 6, 12'}),
            'interest_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001', 'placeholder': '0.05'}),
            'is_flexible': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
