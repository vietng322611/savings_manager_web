from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

def customer_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("/login")

        if not request.user.is_customer:
            if request.user.is_employee:
                return redirect("/employees")
            else:
                return PermissionDenied

        return view_func(request, *args, **kwargs)

    return wrapper

def employee_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("/login")

        if not request.user.is_employee:
            return redirect("/")

        if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
            if not request.user.employee.can_edit:
                raise PermissionDenied

        return view_func(request, *args, **kwargs)

    return wrapper

def employee_write_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("/login")

        if not request.user.is_employee:
            raise PermissionDenied

        if not request.user.employee.can_edit:
            raise PermissionDenied

        return view_func(request, *args, **kwargs)

    return wrapper