from django.urls import path

from . import views

app_name = "usuarios"

# Se montan en /cuentas/ (sistema_clinico/urls.py)
urlpatterns = [
    path("perfil/", views.perfil, name="perfil"),
    path("usuarios/", views.lista, name="lista"),
    # Aquí pueden ir después las rutas del login que trabaja Fer («Mi cuenta», recuperar contraseña…).
]
