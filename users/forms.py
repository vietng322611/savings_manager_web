from allauth.account.forms import SignupForm
from django import forms
from django.db import transaction

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

    def clean_citizen_id(self):
        citizen_id = self.cleaned_data["citizen_id"]
        if Customer.objects.filter(citizen_id=citizen_id).exists():
            raise forms.ValidationError("This citizen ID is already registered.")
        return citizen_id

    def save(self, request):
        with transaction.atomic():
            user = super().save(request)

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

    def clean_citizen_id(self):
        citizen_id = self.cleaned_data["citizen_id"]
        if Customer.objects.filter(
            citizen_id=citizen_id
        ).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This citizen ID is already registered.")

        return citizen_id

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

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if CustomUser.objects.filter(
                email__iexact=email
        ).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("This email is already registered.")

        return email

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if not self.user.check_password(password):
            raise forms.ValidationError("Incorrect password")
        return password

    def save(self):
        self.user.email = self.cleaned_data["email"]
        self.user.save()
