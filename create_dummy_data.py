import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dashboard.settings")
django.setup()

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils.timezone import now

from dashboard.utils import get_parameter
from savings.models import SavingType
from savings.services import create_saving_plan


# TODO: Put the test customer's email here before running this script.
USER_EMAIL = ""

def get_or_create_saving_type(name, duration_months, interest_rate, is_flexible):
    saving_type, _ = SavingType.objects.update_or_create(
        name=name,
        defaults={
            "duration_months": duration_months,
            "interest_rate": Decimal(interest_rate),
            "is_flexible": is_flexible,
            "is_active": True,
        },
    )
    return saving_type


def main():
    if not USER_EMAIL:
        raise ValueError("Set USER_EMAIL in create_dummy_data.py before running this script.")

    CustomUser = get_user_model()
    user = CustomUser.objects.get(email=USER_EMAIL)
    if not user.is_customer:
        raise ValueError(f"{USER_EMAIL} is not a customer user.")

    initial_balance = Decimal(get_parameter("min_initial_deposit", 1_000_000))
    today = now().date()

    three_month_type = get_or_create_saving_type(
        "3 months",
        duration_months=3,
        interest_rate="5.0000",
        is_flexible=False,
    )
    six_month_type = get_or_create_saving_type(
        "6 months",
        duration_months=6,
        interest_rate="5.5000",
        is_flexible=False,
    )
    flexible_type = get_or_create_saving_type(
        "Non-fixed term",
        duration_months=None,
        interest_rate="4.0000",
        is_flexible=True,
    )

    three_month_plan = create_saving_plan(user.customer, three_month_type, initial_balance)
    six_month_plan = create_saving_plan(user.customer, six_month_type, initial_balance)
    flexible_plan = create_saving_plan(user.customer, flexible_type, initial_balance)

    # Make the 3-month fixed-term plan withdrawable immediately.
    three_month_plan.start_date = today - timedelta(days=90)
    three_month_plan.maturity_date = today
    three_month_plan.save(update_fields=["start_date", "maturity_date"])

    # Make the non-fixed-term plan old enough to pass the flexible withdrawal lock.
    flexible_plan.start_date = today - timedelta(days=16)
    flexible_plan.interest_last_applied_on = flexible_plan.start_date
    flexible_plan.save(update_fields=["start_date", "interest_last_applied_on"])

    print("Dummy saving types created or updated.")
    print(f"Created 3-month plan: {three_month_plan.plan_id} (withdrawable now)")
    print(f"Created 6-month plan: {six_month_plan.plan_id}")
    print(f"Created non-fixed-term plan: {flexible_plan.plan_id} (withdrawable now)")

if __name__ == "__main__":
    main()

