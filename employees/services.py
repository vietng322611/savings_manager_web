from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from django.utils.timezone import now

from savings.models import SavingPlan, SavingType, Transaction, TransactionStatus
from savings.services import get_statistics, process_transaction as process_saving_transaction
from users.models import CustomUser

def get_dashboard_reports():
    today = now().date()
    month_start = today.replace(day=1)
    month_label = today.strftime("%Y-%m")

    daily_statistics = get_statistics("day", date=today)
    monthly_statistics = get_statistics("month", month=month_label)
    opened_this_month = SavingPlan.objects.filter(created_at__date__gte=month_start).count()

    return {
        "deposit_report": {
            "deposits": daily_statistics["total_deposit"],
            "withdrawals": daily_statistics["total_withdraw"],
            "difference": daily_statistics["total_deposit"] - daily_statistics["total_withdraw"],
        },
        "saving_plan_report": {
            "opened": opened_this_month,
            "closed": monthly_statistics["closed_count"],
            "difference": opened_this_month - monthly_statistics["closed_count"],
        },
    }

def search_users(query="", user_type=""):
    users = CustomUser.objects.select_related("customer", "employee").all()
    query = query.strip()

    if query:
        users = users.filter(
            Q(email__icontains=query)
            | Q(customer__full_name__icontains=query)
            | Q(customer__citizen_id__icontains=query)
            | Q(employee__role__icontains=query)
        )

    if user_type == "customer":
        users = users.filter(customer__isnull=False)
    elif user_type == "employee":
        users = users.filter(employee__isnull=False)

    return users

def get_user_detail(user_id):
    return get_object_or_404(CustomUser, id=user_id)

def remove_employee_access(user):
    if not user.is_employee:
        raise ValueError("User is not Employee")

    if not user.is_customer:
        user.delete()
        return "deleted"

    user.employee.delete()
    return "updated"

def search_saving_plans(query=""):
    saving_plans = (
        SavingPlan.objects
        .select_related("saving_type", "customer", "customer__user")
        .order_by("-created_at")
    )
    query = query.strip()

    if query:
        saving_plans = saving_plans.filter(
            Q(plan_id__icontains=query)
            | Q(customer__full_name__icontains=query)
            | Q(customer__citizen_id__icontains=query)
            | Q(customer__user__email__icontains=query)
            | Q(saving_type__name__icontains=query)
        )

    return saving_plans

def get_saving_plan_detail(plan_id):
    return get_object_or_404(
        SavingPlan.objects.select_related("saving_type", "customer", "customer__user"),
        plan_id=plan_id,
    )

def get_saving_plan_transactions(saving_plan):
    return (
        saving_plan.transactions
        .select_related("saving_plan")
        .order_by("-timestamp")
    )

def get_saving_types():
    return SavingType.objects.order_by("name")

def get_saving_type_detail(saving_type_id):
    return get_object_or_404(SavingType, pk=saving_type_id)

def get_transaction_detail(transaction_id):
    return get_object_or_404(
        Transaction.objects
        .select_related(
            "saving_plan",
            "saving_plan__saving_type",
            "saving_plan__customer",
            "saving_plan__customer__user",
        ),
        pk=transaction_id
    )

def search_transactions(query="", transaction_type="", transaction_status=""):
    transactions = Transaction.objects.select_related("saving_plan", "saving_plan__saving_type").order_by("-timestamp")
    query = query.strip()

    if query:
        transactions = transactions.filter(
            Q(saving_plan__plan_id__icontains=query)
            | Q(saving_plan__saving_type__name__icontains=query)
        )

    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    if transaction_status:
        transactions = transactions.filter(status=transaction_status)

    return transactions

def process_transaction(transaction: Transaction, new_status: TransactionStatus):
    return process_saving_transaction(transaction, new_status)

def build_report_context(report_type, date_value, month_value):
    today = now().date()
    current_month = today.strftime("%Y-%m")

    if report_type not in {"cash", "plans"}:
        report_type = "cash"

    selected_date = parse_date(date_value or "") or today
    if selected_date > today:
        selected_date = today

    selected_month = month_value or current_month
    try:
        selected_year_value, selected_month_value = selected_month.split("-")
        selected_year_value = int(selected_year_value)
        selected_month_value = int(selected_month_value)
        selected_month_date = parse_date(f"{selected_month}-01")
        current_month_date = today.replace(day=1)
        if selected_month_date is None or selected_month_value < 1 or selected_month_value > 12:
            raise ValueError
        if selected_month_date > current_month_date:
            selected_month = current_month
            selected_year_value = today.year
            selected_month_value = today.month
    except ValueError:
        selected_month = current_month
        selected_year_value = today.year
        selected_month_value = today.month

    if report_type == "cash":
        statistics = get_statistics("day", date=selected_date)
        report = {
            "type": "cash",
            "label": selected_date,
            "deposits": statistics["total_deposit"],
            "withdrawals": statistics["total_withdraw"],
            "difference": statistics["total_deposit"] - statistics["total_withdraw"],
        }
    else:
        statistics = get_statistics("month", month=selected_month)
        opened_count = SavingPlan.objects.filter(
            created_at__year=selected_year_value,
            created_at__month=selected_month_value,
        ).count()
        report = {
            "type": "plans",
            "label": selected_month,
            "opened": opened_count,
            "closed": statistics["closed_count"],
            "difference": opened_count - statistics["closed_count"],
        }

    return {
        "report": report,
        "selected_report": report_type,
        "selected_date": selected_date,
        "selected_month": selected_month,
        "today": today,
        "current_month": current_month,
    }
