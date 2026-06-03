from decimal import Decimal

from django import forms

from savings.models import SavingPlan, SavingType

class SavingPlanCreateForm(forms.Form):
    saving_type = forms.ModelChoiceField(queryset=SavingType.objects.none(), required=True)
    initial_balance = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=True,
        error_messages={
            "required": "Please enter an initial deposit",
            "invalid": "Please enter a valid amount",
            "min_value": "Initial deposit must be positive",
        },
    )

    def __init__(self, *args, active_saving_types=None, min_initial_deposit=1_000_000, **kwargs):
        super().__init__(*args, **kwargs)

        self.min_initial_deposit = min_initial_deposit

        if active_saving_types is not None:
            self.fields["saving_type"].queryset = active_saving_types

    def clean_saving_type(self):
        saving_type = self.cleaned_data["saving_type"]
        if not saving_type:
            raise forms.ValidationError("Please select a saving type")
        return saving_type

    def clean_initial_balance(self):
        initial_balance = self.cleaned_data["initial_balance"]
        if initial_balance < self.min_initial_deposit:
            raise forms.ValidationError(f"Initial deposit must be at least {self.min_initial_deposit}")
        return initial_balance


class SavingPlanActionForm(forms.Form):
    ACTION_CHOICES = [
        ("deposit", "Deposit"),
        ("withdraw", "Withdraw"),
    ]
    action = forms.ChoiceField(choices=ACTION_CHOICES)
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))

class ReportForm(forms.Form):
    PERIOD_CHOICES = [("day", "By Day"), ("month", "By Month"),("year", "By Year")]
    period_type = forms.ChoiceField(choices=PERIOD_CHOICES)
    saving_plan = forms.ModelChoiceField(queryset=SavingPlan.objects.none(), empty_label="Select saving plan")
    date = forms.DateField(required=False,widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, saving_plans_qs=None, **kwargs):
        super().__init__(*args, **kwargs)
        if saving_plans_qs is not None:
            self.fields["saving_plan"].queryset = saving_plans_qs
