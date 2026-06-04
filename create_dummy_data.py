import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dashboard.settings")
django.setup()

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils.timezone import now

from users.models import Customer
from dashboard.utils import get_parameter
from savings.models import (
    SavingType,
    SavingTypeRateHistory,
    Transaction,
    TransactionType,
    TransactionStatus,
)
from savings.services import create_saving_plan, process_transaction


# TODO: Put the test customer's email here before running this script.
USER_EMAIL = ""


def get_or_create_saving_type(
    name: str,
    duration_months: int | None,
    interest_rate: str,
    is_flexible: bool,
):
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


def create_test_saving_plan(
    customer: Customer,
    saving_type: SavingType,
    initial_balance: Decimal,
):
    plan = create_saving_plan(
        customer,
        saving_type,
        initial_balance,
    )

    open_txn = Transaction.objects.get(
        saving_plan=plan,
        transaction_type=TransactionType.OPEN,
    )

    process_transaction(
        open_txn,
        TransactionStatus.SUCCESS,
    )

    plan.refresh_from_db()
    return plan


def age_plan(plan, days):
    """
    Make a plan appear to have been opened 'days' days ago.
    Also updates the OPEN transaction timestamp and flexible-plan
    interest tracking fields.
    """
    old_datetime = now() - timedelta(days=days)
    old_date = old_datetime.date()

    update_fields = ["start_date"]

    plan.start_date = old_date

    if plan.saving_type.is_flexible:
        plan.interest_last_applied_on = old_date
        update_fields.append("interest_last_applied_on")

        SavingTypeRateHistory.objects.filter(
            saving_type=plan.saving_type,
            effective_to__isnull=True,
        ).update(effective_from=old_date)

    plan.save(update_fields=update_fields)

    plan.transactions.filter(transaction_type=TransactionType.OPEN).update(timestamp=old_datetime)

    return old_date


def main():
    if not USER_EMAIL:
        raise ValueError(
            "Set USER_EMAIL in create_dummy_data.py before running this script."
        )

    CustomUser = get_user_model()

    user = CustomUser.objects.get(email=USER_EMAIL)

    if not user.is_customer:
        raise ValueError(
            f"{USER_EMAIL} is not a customer user."
        )

    initial_balance = Decimal(
        get_parameter("min_initial_deposit", 1_000_000)
    )

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
        interest_rate="0.5000",
        is_flexible=True,
    )

    three_month_plan = create_test_saving_plan(
        user.customer,
        three_month_type,
        initial_balance,
    )

    six_month_plan = create_test_saving_plan(
        user.customer,
        six_month_type,
        initial_balance,
    )

    flexible_plan = create_test_saving_plan(
        user.customer,
        flexible_type,
        initial_balance,
    )

    age_plan(three_month_plan, 90)

    three_month_plan.maturity_date = today
    three_month_plan.save(update_fields=["maturity_date"])

    age_plan(flexible_plan, 30)

    print("Dummy saving types created or updated.\n")
    print(f"Created 3-month plan: {three_month_plan.plan_id} (withdrawable now)")
    print(f"Created 6-month plan: {six_month_plan.plan_id}")
    print(f"Created non-fixed-term plan: {flexible_plan.plan_id} (deposit, withdraw, and interest testing ready)")


if __name__ == "__main__":
    main()