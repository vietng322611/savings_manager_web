from django.db import transaction
from decimal import Decimal
from datetime import date
from django.db.models import F, Sum

from dashboard.utils import get_parameter
from django.db.models import QuerySet
from django.utils.timezone import now

from savings.models import (
    SavingPlan,
    SavingPlanStatus,
    SavingType,
    SavingTypeRateHistory,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from users.models import CustomUser, Customer


def _add_months(d: date, months: int) -> date:
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    # keep safe day in target month
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)

def get_all_saving_plans():
    return SavingPlan.objects.all()

def get_active_saving_types():
    return SavingType.objects.filter(is_active=True).order_by("name")

def create_saving_plan(
    customer: Customer,
    saving_type: SavingType,
    initial_balance: Decimal
) -> SavingPlan:
    min_initial_deposit = Decimal(get_parameter("min_initial_deposit", 1_000_000))
    if initial_balance < min_initial_deposit:
        raise ValueError(f"Minimum balance is {min_initial_deposit:,.0f}")

    maturity_date = None
    if not saving_type.is_flexible and saving_type.duration_months:
        maturity_date = _add_months(now().date(), saving_type.duration_months)

    with transaction.atomic():
        saving_plan = SavingPlan.objects.create(
            balance=initial_balance,
            interest_rate=saving_type.interest_rate,
            status=SavingPlanStatus.PENDING,
            # Start accrual tracking only when the plan is approved.
            interest_last_applied_on=None,
            maturity_date=maturity_date,
            saving_type=saving_type,
            customer=customer,
        )

        save_transaction(
            saving_plan,
            TransactionType.OPEN,
            Decimal("0.00"),
            initial_balance,
            initial_balance,
            status=TransactionStatus.PENDING,
        )

    return saving_plan

def get_plan_by_id(plan_id: str) -> SavingPlan | None:
    return SavingPlan.objects.get(plan_id=plan_id)

def get_plans_by_user(user: CustomUser) -> QuerySet[SavingPlan, SavingPlan]:
    if not user.is_customer:
        return SavingPlan.objects.none()
    return SavingPlan.objects.filter(customer=user.customer).select_related("saving_type").order_by("plan_id")

# get by name is unreliable
def get_plans_by_citizen_id(citizen_id: str) -> QuerySet[SavingPlan, SavingPlan]:
    return SavingPlan.objects.filter(customer__citizen_id=citizen_id)

# rename the form later
def process_transaction_form(customer: Customer, cleaned_data):
    action = cleaned_data["action"]

    if action == "create":
        return create_saving_plan(
            customer=customer,
            saving_type=cleaned_data["saving_type"],
            initial_balance=cleaned_data["initial_balance"],
        )

    saving_plan = cleaned_data["saving_plan"]
    amount = cleaned_data["amount"]

    if action == "deposit":
        deposit(saving_plan, amount)
    else:
        withdraw(saving_plan, amount)

    return saving_plan

def generate_statistics(cleaned_data, month=None, year=None):
    return get_statistics(
        period=cleaned_data["period_type"],
        saving_plan=cleaned_data["saving_plan"],
        day=cleaned_data.get("date"),
        month=month,
        year=year,
    )

def get_customer_transactions_context(user: CustomUser, selected_plan_id: str):
    saving_plans = get_plans_by_user(user)
    selected_plan = None
    transactions = Transaction.objects.none()

    if selected_plan_id:
        selected_plan = saving_plans.filter(plan_id=selected_plan_id).first()
        if selected_plan:
            transactions = selected_plan.transactions.order_by("-timestamp")

    return {
        "saving_plans": saving_plans,
        "selected_plan": selected_plan,
        "selected_plan_id": selected_plan_id,
        "transactions": transactions,
    }

def deposit(saving_plan: SavingPlan, amount: Decimal):
    minimum_deposit = Decimal(get_parameter("min_additional_deposit", 100_000))
    if amount < minimum_deposit:
        raise ValueError(
            f"Minimum deposit is {minimum_deposit:,.0f}"
        )

    with transaction.atomic():
        saving_plan.refresh_from_db()

        if saving_plan.status != SavingPlanStatus.ACTIVE:
            raise ValueError("Saving plan is not active yet")

        if not saving_plan.saving_type.is_flexible:
            raise ValueError("Additional deposits are not allowed for fixed-term saving plans")

        # Deposit requests are created first and must be approved by an employee.
        balance_before = saving_plan.balance
        balance_after = balance_before + amount

        save_transaction(
            saving_plan,
            TransactionType.DEPOSIT,
            balance_before,
            amount,
            balance_after,
            status=TransactionStatus.PENDING,
        )

def withdraw(saving_plan: SavingPlan, amount: Decimal) -> Decimal:
    """
    fixed-term: - only allow withdrawal after maturity day and have to withdraw all balances
                - 1-year interest = balance * respective rate
                - after maturity, the interest rate will be a non-fixed-term interest rate
                - close after withdrawal
    non-fixed-term: only allow withdrawal after 15 days since deposit, can withdraw partial
    calculate balance after maturity before withdrawal
    """

    min_deposit_days_flexible = int(get_parameter("min_deposit_days_flexible", 15))

    with transaction.atomic():
        saving_plan.refresh_from_db()
        today = now().date()

        if saving_plan.status != SavingPlanStatus.ACTIVE:
            raise ValueError("Saving plan is not active yet")

        if not saving_plan.saving_type.is_flexible: # fixed-term
            if saving_plan.maturity_date is None:
                raise ValueError("Fixed-term saving plan is missing maturity date")
            if today < saving_plan.maturity_date:
                raise ValueError("Cannot withdraw before maturity")

            balance = saving_plan.balance
            save_transaction(
                saving_plan,
                TransactionType.WITHDRAW,
                balance,
                balance,
                Decimal("0.00"),
                status=TransactionStatus.PENDING,
            )

            return balance
        else:
            if saving_plan.start_date is None:
                raise ValueError("Saving plan has no start date")

            # 15-day lock
            days_since_start = (today - saving_plan.start_date).days
            if days_since_start < min_deposit_days_flexible:
                raise ValueError(f"Cannot withdraw within {min_deposit_days_flexible} days after deposited")

            if amount > saving_plan.balance:
                raise ValueError("Insufficient balance")

            # Withdrawal requests are created first and must be approved by an employee.
            # Interest is intentionally not applied until approval time.
            balance_before = saving_plan.balance
            balance_after = balance_before - amount

            save_transaction(
                saving_plan,
                TransactionType.WITHDRAW,
                balance_before,
                amount,
                balance_after,
                status=TransactionStatus.PENDING,
            )

            return amount

def apply_interest(saving_plan: SavingPlan):
    # Fixed-term: estimate payout as principal + simple interest.
    if not saving_plan.saving_type.is_flexible:
        return saving_plan.balance + (saving_plan.balance * saving_plan.interest_rate / 100)

    today = now().date()
    from_date = saving_plan.interest_last_applied_on or saving_plan.start_date

    # Nothing to accrue if we've already applied through today.
    if from_date >= today:
        return saving_plan.balance

    # Pull all historical rate windows that may overlap the accrual range.
    histories = SavingTypeRateHistory.objects.filter(
        saving_type=saving_plan.saving_type,
        effective_from__lt=today
    ).order_by("effective_from")

    interest = Decimal("0")

    if histories.exists():
        for h in histories:
            seg_start = max(from_date, h.effective_from)
            seg_end = min(today, h.effective_to or today)
            if seg_end <= seg_start:
                continue

            days = (seg_end - seg_start).days
            # Simple daily interest, annualized by 365 days.
            interest += saving_plan.balance * (h.interest_rate / Decimal("100")) * (Decimal(days) / Decimal("365"))
    else:
        # Backward compatibility when no history rows exist yet.
        days = (today - from_date).days
        interest += saving_plan.balance * (saving_plan.interest_rate / Decimal("100")) * (Decimal(days) / Decimal("365"))

    saving_plan.balance += interest
    saving_plan.interest_last_applied_on = today
    # Keep the saving plan snapshot in sync with current saving type display rate.
    saving_plan.interest_rate = saving_plan.saving_type.interest_rate
    saving_plan.save(update_fields=["balance", "interest_last_applied_on", "interest_rate"])
    return saving_plan.balance

def close_saving_plan(saving_plan: SavingPlan):
    """ Should be called inside an atomic transaction. """

    save_transaction(
        saving_plan,
        TransactionType.CLOSE,
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00")
    )
    saving_plan.soft_delete()

def change_saving_type_rate(
    saving_type: SavingType,
        new_rate: Decimal,
        effective_from: date | None = None
) -> SavingType:
    """
        Helper function to safely change rate while preserving history windows.
    """

    effective_from = effective_from or now().date()

    with transaction.atomic():
        SavingTypeRateHistory.objects.filter(
            saving_type=saving_type,
            effective_to__isnull=True
        ).update(effective_to=effective_from)

        SavingTypeRateHistory.objects.create(
            saving_type=saving_type,
            interest_rate=new_rate,
            effective_from=effective_from,
            effective_to=None
        )

        saving_type.interest_rate = new_rate
        saving_type.save(update_fields=["interest_rate"])

    return saving_type

def get_statistics(period: str, saving_plan=None, day=None, month=None, year=None):
    transactions = Transaction.objects.filter(status=TransactionStatus.SUCCESS)

    if saving_plan is not None:
        transactions = transactions.filter(saving_plan=saving_plan)
    
    if period == "day":
        if day:
            transactions = transactions.filter(timestamp__date=day)
    elif period == "month":
        if month:
            try:
                year_val, month_val = month.split("-")
                transactions = transactions.filter(timestamp__year=int(year_val), timestamp__month=int(month_val))
            except ValueError:
                pass
    elif period == "year":
        if year:
            transactions = transactions.filter(timestamp__year=int(year))

    total_open = transactions.filter(transaction_type=TransactionType.OPEN).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    total_deposit = transactions.filter(transaction_type=TransactionType.DEPOSIT).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    total_withdraw = transactions.filter(transaction_type=TransactionType.WITHDRAW).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    total_close = transactions.filter(transaction_type=TransactionType.CLOSE).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    total_income = total_open + total_deposit
    total_expense = total_withdraw + total_close

    if period == "day":
        label = str(day) if day else "N/A"
    elif period == "month":
        label = month if month else "N/A"
    elif period == "year":
        label = str(year) if year else "N/A"
    else:
        label = "N/A"

    return {
        "label": label,
        "plan_id": saving_plan.plan_id if saving_plan else "All",
        "customer_name": (
            saving_plan.customer.full_name
            if saving_plan and getattr(saving_plan, "customer", None)
            else "All saving plans"
        ),
        "total_open": total_open,
        "total_deposit": total_deposit,
        "total_withdraw": total_withdraw,
        "total_close": total_close,
        "opened_count": transactions.filter(transaction_type=TransactionType.OPEN).count(),
        "closed_count": transactions.filter(transaction_type=TransactionType.CLOSE).count(),
        "total_income": total_income,
        "total_expense": total_expense,
        "difference": total_income - total_expense
    }

def save_transaction(
    saving_plan: SavingPlan,
    transaction_type: TransactionType,
    balance_before: Decimal,
    amount: Decimal,
    balance_after: Decimal,
    status: TransactionStatus = TransactionStatus.SUCCESS,
):
    return Transaction.objects.create(
        saving_plan=saving_plan,
        transaction_type=transaction_type,
        status=status,
        balance_before=balance_before,
        amount=amount,
        balance_after=balance_after
    )


def process_transaction(txn: Transaction, new_status: TransactionStatus) -> Transaction:
    """
    Process an employee decision for a pending transaction.
    SUCCESS applies the transaction effects.
    CANCELED rejects it without changing balances.
    """
    with transaction.atomic():
        txn = (
            Transaction.objects.select_for_update()
            .select_related("saving_plan", "saving_plan__saving_type")
            .get(pk=txn.pk)
        )
        if txn.status != TransactionStatus.PENDING:
            return txn

        if new_status == TransactionStatus.CANCELED:
            txn.status = TransactionStatus.CANCELED
            txn.save(update_fields=["status"])
            if txn.transaction_type == TransactionType.OPEN:
                saving_plan = txn.saving_plan
                saving_plan.status = SavingPlanStatus.CLOSED
                saving_plan.save(update_fields=["status"])
            return txn

        if new_status != TransactionStatus.SUCCESS:
            raise ValueError("Unsupported transaction status")

        saving_plan = txn.saving_plan
        saving_plan.refresh_from_db()
        today = now().date()

        if txn.transaction_type == TransactionType.OPEN:
            if saving_plan.status != SavingPlanStatus.PENDING:
                return txn

            saving_plan.status = SavingPlanStatus.ACTIVE
            saving_plan.start_date = today
            if saving_plan.saving_type.is_flexible:
                saving_plan.interest_last_applied_on = today

            SavingPlan.objects.filter(pk=saving_plan.pk).update(
                balance=txn.amount,
                status=SavingPlanStatus.ACTIVE,
                start_date=today,
                interest_last_applied_on=today if saving_plan.saving_type.is_flexible else None,
            )
            saving_plan.refresh_from_db(fields=["balance", "status", "start_date", "interest_last_applied_on"])

            balance_before = Decimal("0.00")
            balance_after = txn.amount

        elif txn.transaction_type == TransactionType.DEPOSIT:
            if not saving_plan.saving_type.is_flexible:
                raise ValueError("Additional deposits are not allowed for fixed-term saving plans")

            apply_interest(saving_plan)
            balance_before = saving_plan.balance
            balance_after = balance_before + txn.amount

            SavingPlan.objects.filter(pk=saving_plan.pk).update(balance=F("balance") + txn.amount)
            saving_plan.refresh_from_db(fields=["balance"])

        elif txn.transaction_type == TransactionType.WITHDRAW:
            if saving_plan.saving_type.is_flexible:
                if saving_plan.start_date is None:
                    raise ValueError("Saving plan has no start date")
                min_deposit_days_flexible = int(get_parameter("min_deposit_days_flexible", 15))
                days_since_start = (today - saving_plan.start_date).days
                if days_since_start < min_deposit_days_flexible:
                    raise ValueError(f"Cannot withdraw within {min_deposit_days_flexible} days after deposited")

                apply_interest(saving_plan)
                balance_before = saving_plan.balance

                if txn.amount > balance_before:
                    raise ValueError("Insufficient balance")

                balance_after = balance_before - txn.amount
                SavingPlan.objects.filter(pk=saving_plan.pk).update(balance=F("balance") - txn.amount)
                saving_plan.refresh_from_db(fields=["balance"])

                if balance_after == 0:
                    close_saving_plan(saving_plan)

            else:
                if saving_plan.maturity_date is None:
                    raise ValueError("Fixed-term saving plan is missing maturity date")
                if today < saving_plan.maturity_date:
                    raise ValueError("Cannot withdraw before maturity")

                balance_before = apply_interest(saving_plan)
                balance_after = Decimal("0.00")

                SavingPlan.objects.filter(pk=saving_plan.pk).update(balance=Decimal("0.00"))
                saving_plan.refresh_from_db(fields=["balance"])
                close_saving_plan(saving_plan)

        else:
            raise ValueError("Unsupported transaction type")

        txn.balance_before = balance_before
        txn.balance_after = balance_after
        txn.status = TransactionStatus.SUCCESS
        txn.save(update_fields=["balance_before", "balance_after", "status"])
        return txn