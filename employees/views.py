from django.http import HttpResponseBadRequest, HttpResponseServerError
from django.shortcuts import render, redirect
from django.db import transaction

from dashboard.decorators import employee_required, employee_write_required
from dashboard.flash import flash_success, flash_error
from savings.models import SavingType, TransactionType, TransactionStatus
from users.forms import InformationChangeForm
from .forms import EmployeeChangeForm, UserCreateForm, SavingTypeEditForm
from .services import (
    build_report_context,
    get_dashboard_reports,
    get_saving_plan_detail,
    get_saving_plan_transactions,
    get_saving_type_detail,
    get_user_detail,
    remove_employee_access,
    search_saving_plans,
    search_transactions,
    search_users, search_saving_types, get_transaction_detail, process_transaction,
)
from savings.services import change_saving_type_rate

@employee_required
def employee_dashboard(request):
    return render(request, "employees/dashboard.html", get_dashboard_reports())

@employee_required
def manage_users(request):
    users = search_users(
        query=request.GET.get("search", ""),
        user_type=request.GET.get("type", ""),
    )

    return render(request, "employees/users/users.html", {
        "users": users,
    })

@employee_required
def manage_user_detail(request, user_id):
    selected_user = get_user_detail(user_id)
    if selected_user.is_customer:
        customer_form = InformationChangeForm(instance=selected_user.customer)
    else:
        customer_form = None

    employee_form = EmployeeChangeForm(user=selected_user)

    if request.method == "POST":
        match request.POST.get("form_type"):
            case "customer":
                customer_form = InformationChangeForm(request.POST, instance=selected_user.customer)
                if customer_form.is_valid():
                    customer_form.save()

                    flash_success(request, "Customer information updated successfully.")
                    return redirect(request.path)
            case "employee":
                action = request.POST.get("action")
                if action == "remove":
                    try:
                        result = remove_employee_access(selected_user)
                        if result == "deleted":
                            flash_success(request, "User deleted successfully.")
                            return redirect("manage_users")

                        flash_success(request, "Employee access updated successfully.")
                        return redirect(request.path)
                    except ValueError as exc:
                        return HttpResponseBadRequest(str(exc))
                else:
                    employee_form = EmployeeChangeForm(request.POST, user=selected_user)
                    if employee_form.is_valid():
                        employee_form.save()

                        flash_success(request, "Employee access updated successfully.")
                        return redirect(request.path)

    return render(request, "employees/users/user_detail.html", {
        "selected_user": selected_user,
        "customer_form": customer_form,
        "employee_form": employee_form,
    })

@employee_write_required
def user_create(request):
    form = UserCreateForm()
    if request.method == "POST":
        try:
            form = UserCreateForm(request.POST)
            if form.is_valid():
                form.save()

                flash_success(request, "Successfully created user.")
                return redirect("manage_users")
        except Exception:
            flash_error(request, "An error occurred while creating the user.")

    return render(request, "employees/users/user_create.html", { "form": form })

@employee_required
def manage_reports(request):
    try:
        selected_report = request.GET.get("report", "cash")

        context = build_report_context(
            selected_report,
            request.GET.get("date", ""),
            request.GET.get("month", ""),
        )
        return render(request, "employees/savings/reports.html", context)
    except Exception as e:
        # there aren't any errors on this page that are not a critical server error
        # returning 5xx instead of showing error is ok here
        return HttpResponseServerError(str(e))

@employee_required
def manage_saving_plans(request):
    search = request.GET.get("search", "").strip()
    saving_plans = search_saving_plans(search)

    return render(request,"employees/savings/saving_plans.html", {
        "saving_plans": saving_plans,
        "search": search,
    })

@employee_required
def manage_saving_plan_detail(request, plan_id):
    saving_plan = get_saving_plan_detail(plan_id)
    transactions = get_saving_plan_transactions(saving_plan)

    return render(request,"employees/savings/saving_plan_detail.html",{
        "saving_plan": saving_plan,
        "transactions": transactions,
    })

@employee_required
def manage_saving_types(request):
    saving_types = search_saving_types(
        query=request.GET.get("search", ""),
        is_active=request.GET.get("status", True),
    )

    return render(request, "employees/savings/saving_types.html", {
        "saving_types": saving_types,
    })

@employee_write_required
def manage_saving_type_detail(request, saving_type_id):
    saving_type = get_saving_type_detail(saving_type_id)
    form = SavingTypeEditForm(instance=saving_type)

    if request.method == "POST":
        try:
            form = SavingTypeEditForm(request.POST, instance=saving_type)
            if form.is_valid():
                new_duration = form.cleaned_data["duration_months"]
                duration_changed = new_duration != saving_type.duration_months
                flexible_changed = form.cleaned_data["is_flexible"] != saving_type.is_flexible
                rate_changed = form.cleaned_data["interest_rate"] != saving_type.interest_rate

                if duration_changed and new_duration is not None:
                    if SavingType.objects.filter(
                        duration_months=new_duration,
                    ).exclude(pk=saving_type.pk).exists():
                        form.add_error(
                            "duration_months",
                            "Another active saving type already uses this duration.",
                        )
                    else:
                        with transaction.atomic():
                            # Keep old product definition for audit/history.
                            saving_type.is_active = False
                            saving_type.save(update_fields=["is_active"])

                            new_saving_type = form.save(commit=False)
                            new_saving_type.pk = None
                            new_saving_type.save()

                        flash_success(request, "Saving type updated successfully.")
                        return redirect("manage_saving_type_detail", saving_type_id=new_saving_type.id)
                elif flexible_changed:
                    with transaction.atomic():
                        # Version the saving type instead of mutating the semantics in place.
                        saving_type.is_active = False
                        saving_type.save(update_fields=["is_active"])

                        new_saving_type = form.save(commit=False)
                        new_saving_type.pk = None
                        new_saving_type.save()

                    flash_success(request, "Saving type updated successfully.")
                    return redirect("manage_saving_type_detail", saving_type_id=new_saving_type.id)
                else:
                    with transaction.atomic():
                        if rate_changed:
                            change_saving_type_rate(saving_type, form.cleaned_data["interest_rate"])

                        SavingType.objects.filter(pk=saving_type.pk).update(
                            name=form.cleaned_data["name"],
                            duration_months=new_duration,
                            is_flexible=form.cleaned_data["is_flexible"],
                            is_active=form.cleaned_data["is_active"],
                        )

                    flash_success(request, "Saving type updated successfully.")
                    return redirect("manage_saving_type_detail", saving_type_id=saving_type.id)
        except Exception:
            flash_error(request, "An error occurred while updating the saving type.")

    return render(request,"employees/savings/saving_type_detail.html",{
        "form": form,
        "saving_type": saving_type,
    })

@employee_write_required
def saving_type_create(request):
    form = SavingTypeEditForm()

    if request.method == "POST":
        try:
            form = SavingTypeEditForm(request.POST)
            if form.is_valid():
                form.save()
                flash_success(request, "Saving type created successfully.")
                return redirect("manage_saving_types")
        except Exception:
            flash_error(request, "An error occurred while creating the saving type.")

    return render(request, "employees/savings/saving_type_detail.html", {
        "form": form,
    })

@employee_required
def manage_transactions(request):
    transactions = search_transactions(
        query=request.GET.get("search", ""),
        transaction_type=request.GET.get("type", ""),
        status=request.GET.get("status", ""),
    )

    return render(request, "employees/savings/transactions.html", {
        "transactions": transactions,
        "transaction_types": TransactionType.choices,
        "status": TransactionStatus.choices,
    })

@employee_write_required
def manage_transaction_detail(request, transaction_id):
    selected_transaction = get_transaction_detail(transaction_id)

    if request.method == "POST":
        action = request.POST.get("action")
        try:
            match action:
                case "approve":
                    process_transaction(selected_transaction, TransactionStatus.SUCCESS)
                    flash_success(request, "Transaction approved successfully.")

                case "cancel":
                    process_transaction(selected_transaction, TransactionStatus.CANCELED)
                    flash_success(request, "Transaction cancelled successfully.")
        except Exception as e:
            print(str(e))
            flash_error(request, "An error occurred while processing the transaction.")

        return redirect(request.path, transaction_id=selected_transaction.id)

    return render(request,"employees/savings/transaction_detail.html",{
        "transaction": selected_transaction,
    })
