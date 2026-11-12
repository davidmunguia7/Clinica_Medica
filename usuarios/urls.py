from django.urls import path

from . import views

app_name = "usuarios"

# Se montan en /cuentas/ (sistema_clinico/urls.py). Entrar y salir también están ahí,
# en /cuentas/entrar/ y /cuentas/salir/, con los nombres «login» y «logout» de siempre.
urlpatterns = [
    path("cambiar-contrasena/", views.cambiar_clave, name="cambiar_clave"),
    path("sigo-aqui/", views.sigo_aqui, name="sigo_aqui"),
    path("perfil/", views.perfil, name="perfil"),
    path("usuarios/", views.lista, name="lista"),
    path("usuarios/<int:pk>/restablecer-contrasena/", views.restablecer_clave, name="restablecer_clave"),
    path("usuarios/<int:pk>/desbloquear/", views.desbloquear, name="desbloquear"),
    path("accesos/", views.bitacora, name="bitacora"),
]
