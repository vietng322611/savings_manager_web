from django.urls import path
from . import views

urlpatterns = [
    path("", views.employee_dashboard, name="employee_dashboard"),
    path("users/", views.manage_users, name="manage_users"),
    path("users/<int:user_id>/", views.manage_user_detail, name="manage_user_profile"),
    path("user-create/", views.user_create, name="user_create"),
    path("savings/", views.manage_saving_plans, name="manage_saving_plans"),
    path("savings/<str:plan_id>/",views.manage_saving_plan_detail,name="manage_saving_plan_detail",),
    path("saving-types/", views.manage_saving_types, name="manage_saving_types"),
    path("saving-types/create/", views.saving_type_create, name="saving_type_create"),
    path("saving-types/<int:saving_type_id>/", views.manage_saving_type_detail, name="manage_saving_type_detail"),
    path("transactions/", views.manage_transactions, name="manage_transactions"),
    path("transactions/<int:transaction_id>/", views.manage_transaction_detail, name="manage_transaction_detail"),
    path("reports/", views.manage_reports, name="manage_reports"),
]
