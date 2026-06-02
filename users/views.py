from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import redirect, render

from dashboard.decorators import customer_required
from dashboard.flash import flash_success
from users.forms import EmailChangeForm, InformationChangeForm

@customer_required
def profile(request):
    information_form = InformationChangeForm(instance=request.user.customer)
    password_form = PasswordChangeForm(request.user)
    email_form = EmailChangeForm(user=request.user)

    if request.method == "POST":
        match request.POST.get("form_type"):
            case "information":
                information_form = InformationChangeForm(request.POST, instance=request.user.customer)
                if information_form.is_valid():
                    information_form.save()

                    flash_success(request, "Information updated successfully.")
                    return redirect(request.path)
            case "password":
                password_form = PasswordChangeForm(request.user, request.POST)
                if password_form.is_valid():
                    user = password_form.save()
                    update_session_auth_hash(request, user)

                    flash_success(request, "Password updated successfully.")
                    return redirect(request.path)
            case "email":
                email_form = EmailChangeForm(request.POST, user=request.user)
                if email_form.is_valid():
                    email_form.save()

                    flash_success(request, "Email updated successfully.")
                    return redirect(request.path)

    return render(request, "account/profile.html", {
        "information_form": information_form,
        "password_form": password_form,
        "email_form": email_form,
    })