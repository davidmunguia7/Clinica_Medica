from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "reportes"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="reportes:mensual"), name="inicio"),
    path("mensual/", views.mensual, name="mensual"),
]
