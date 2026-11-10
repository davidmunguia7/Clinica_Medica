from django.urls import path

from . import views

app_name = "usuarios"

urlpatterns = [
    path("", views.lista, name="lista"),
    # Aquí pueden ir después las rutas del login que trabaja Fer («Mi cuenta», recuperar contraseña…).
]
