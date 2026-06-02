from allauth.account.forms import SignupForm
from django import forms
from django.db import IntegrityError, transaction

from .models import Customer, CustomUser

class CustomSignupForm(SignupForm):
    full_name = forms.CharField(max_length=50)
    citizen_id = forms.CharField(max_length=12)
    address = forms.CharField(max_length=100)

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("This email is already registered.")
        return email

    def save(self, request):
        with transaction.atomic():
            try:
                user = super().save(request)
            except IntegrityError:
                raise forms.ValidationError({"email": "This email is already registered."})

            Customer.objects.create(
                user=user,
                full_name=self.cleaned_data["full_name"],
                citizen_id=self.cleaned_data["citizen_id"],
                address=self.cleaned_data["address"],
            )

            return user

class InformationChangeForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            "full_name",
            "citizen_id",
            "address",
        ]

class EmailChangeForm(forms.Form):
    email = forms.EmailField(label="New email")
    confirm_email = forms.EmailField(label="Confirm email")
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()

        if not cleaned_data:
            return cleaned_data

        email = cleaned_data.get("email")
        confirm_email = cleaned_data.get("confirm_email")

        if email and confirm_email and email != confirm_email:
            self.add_error("confirm_email", "Emails do not match")

        return cleaned_data

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if not self.user.check_password(password):
            raise forms.ValidationError("Incorrect password")
        return password

    def save(self):
        self.user.email = self.cleaned_data["email"]
        self.user.save()
