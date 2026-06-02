from django.urls import path
from . import views

urlpatterns = [
    path("", views.saving_plans, name="saving_plans"),
    path("create/", views.saving_plan_create, name="saving_plan_create"),
    path("<str:plan_id>/", views.saving_plan_detail, name="saving_plan_detail"),
]
