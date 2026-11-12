"""Reglas de la sesión que se revisan en cada pantalla (se activan en MIDDLEWARE de settings.py)."""
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse

ULTIMA_ACTIVIDAD = "ultima_actividad"


class CierrePorInactividad:
    """Cierra la sesión si pasan SESION_MINUTOS_DE_INACTIVIDAD minutos sin usar el sistema.

    Así nadie usa la cuenta de otro si la computadora de la clínica queda abierta. Mientras la
    persona escribe en una pantalla (una consulta larga, por ejemplo), la página avisa al servidor
    que sigue ahí; y dos minutos antes de cerrar muestra un aviso (theme/templates/base.html).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        limite = settings.SESION_MINUTOS_DE_INACTIVIDAD * 60
        request.segundos_de_inactividad = limite
        if request.user.is_authenticated:
            ahora = time.time()
            ultima = request.session.get(ULTIMA_ACTIVIDAD)
            if ultima is not None and ahora - ultima > limite:
                request.cierre_por_inactividad = True  # para la bitácora (usuarios/accesos.py)
                logout(request)
                messages.info(
                    request,
                    f"Por seguridad, su sesión se cerró porque pasaron {settings.SESION_MINUTOS_DE_INACTIVIDAD} "
                    "minutos sin usar el sistema. Vuelva a entrar.",
                )
                # Sin sesión, la pantalla de entrar se encarga (y regresa aquí después)
            else:
                request.session[ULTIMA_ACTIVIDAD] = ahora
        return self.get_response(request)


class CambioDeClaveObligatorio:
    """Con una contraseña temporal no se puede hacer nada hasta crear la propia."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = request.user
        if usuario.is_authenticated and getattr(usuario, "debe_cambiar_clave", False):
            permitidas = {reverse("usuarios:cambiar_clave"), reverse("usuarios:sigo_aqui"), reverse("logout")}
            if request.path not in permitidas:
                return redirect("usuarios:cambiar_clave")
        return self.get_response(request)
