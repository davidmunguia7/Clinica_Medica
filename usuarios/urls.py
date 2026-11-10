from django.urls import path

from . import views

app_name = "usuarios"

urlpatterns = [
    path("perfil/", views.perfil, name="perfil"),
]
