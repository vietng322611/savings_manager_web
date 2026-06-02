from decimal import Decimal

from django.http import Http404
from django.shortcuts import redirect, render
from django.db.models import Q

from dashboard.decorators import customer_required
from dashboard.flash import flash_success
from dashboard.utils import get_parameter
from savings.forms import (
    SavingPlanCreateForm,
    SavingPlanActionForm,
)
from savings.services import (
    create_saving_plan,
    deposit,
    get_active_saving_types,
    get_plan_by_id,
    get_plans_by_user,
    withdraw,
)

@customer_required
def saving_plans(request):
    saving_plans = get_plans_by_user(request.user)
    search = request.GET.get("search", "").strip()
    if search:
        saving_plans = saving_plans.filter(
            Q(plan_id__icontains=search)
            | Q(saving_type__name__icontains=search)
        )

    return render(request,"savings/saving_plans.html",{
        "saving_plans": saving_plans,
        "search": search,
    })

@customer_required
def saving_plan_detail(request, plan_id):
    saving_plan = get_plan_by_id(plan_id)
    if saving_plan is None:
        return Http404("Saving plan not found")

    action_form = SavingPlanActionForm(prefix="action")

    if request.method == "POST":
        action_form = SavingPlanActionForm(request.POST, prefix="action")
        if action_form.is_valid():
            action = action_form.cleaned_data["action"]
            amount = action_form.cleaned_data["amount"]
            if action == "deposit":
                deposit(saving_plan, amount)
                flash_success(request, f"Created request to deposit {amount}")
            else:
                withdraw(saving_plan, amount)
                flash_success(request, f"Created request to withdraw {amount}")

            return redirect("saving_plan_detail", plan_id=plan_id)

    transactions = saving_plan.transactions.order_by("-timestamp")
    return render(request, "savings/saving_plan_detail.html", {
        "saving_plan": saving_plan,
        "transactions": transactions,
        "action_form": action_form,
    })

@customer_required
def saving_plan_create(request):
    saving_types = get_active_saving_types()
    min_initial_deposit = Decimal(get_parameter("min_initial_deposit", 1_000_000))
    form = SavingPlanCreateForm(active_saving_types=saving_types, min_initial_deposit=min_initial_deposit)

    if request.method == "POST":
        form = SavingPlanCreateForm(request.POST,
                                    active_saving_types=saving_types, min_initial_deposit=min_initial_deposit)
        if form.is_valid():
            create_saving_plan(
                customer=request.user.customer,
                saving_type=form.cleaned_data["saving_type"],
                initial_balance=form.cleaned_data["initial_balance"],
            )

            flash_success(request, "Created request to open new saving plan.")
            return redirect("saving_plans")

    return render(request,"savings/saving_plan_create.html", {
        "form": form,
        "saving_types": saving_types,
        "min_initial_deposit": min_initial_deposit,
        "customer": request.user.customer,
    })
