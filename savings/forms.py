from decimal import Decimal

from django import forms

from savings.models import SavingPlan, SavingType

class SavingPlanCreateForm(forms.Form):
    saving_type = forms.ModelChoiceField(queryset=SavingType.objects.none(), required=True)
    initial_balance = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), required=True)

    def __init__(self, *args, active_saving_types=None, min_initial_deposit=None, **kwargs):
        super().__init__(*args, **kwargs)

        if active_saving_types is not None:
            self.fields["saving_type"].queryset = active_saving_types

        if min_initial_deposit is not None:
            self.fields["initial_balance"].initial = min_initial_deposit

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("saving_type"):
            self.add_error("saving_type", "This field is required.")
        if not cleaned_data.get("initial_balance"):
            self.add_error("initial_balance", "This field is required.")
        return cleaned_data

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
