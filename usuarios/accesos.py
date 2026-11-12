"""Bitácora de accesos y bloqueo por intentos fallidos.

- Cada entrada, salida, intento fallido y cambio de contraseña queda en la tabla Acceso.
  Se anota solo, con las señales de Django (abajo): no importa si se entró por
  /cuentas/entrar/ o por el panel de administración.
- Si alguien escribe mal la contraseña INTENTOS_PERMITIDOS veces en MINUTOS_DE_BLOQUEO
  minutos, ese usuario queda bloqueado MINUTOS_DE_BLOQUEO minutos (aunque después escriba
  la contraseña correcta). Lo aplica usuarios/backends.py (BloqueoPorIntentos).
  También se bloquean los usuarios que no existen, para no revelar cuáles sí existen.
- El Administrador puede desbloquear antes de tiempo o restablecer la contraseña.
"""
import math
import secrets
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from django.utils import timezone

from .models import Acceso, Usuario

Tipo = Acceso.Tipo

INTENTOS_PERMITIDOS = 5
MINUTOS_DE_BLOQUEO = 15

# Lo que corta una racha de intentos fallidos: entrar bien, que el Administrador
# restablezca la contraseña o desbloquee, o que el bloqueo ya se haya aplicado.
_CORTAN_LA_RACHA = (Tipo.ENTRADA, Tipo.CLAVE_RESTABLECIDA, Tipo.DESBLOQUEO, Tipo.BLOQUEO)


def _ip(request):
    return (request.META.get("REMOTE_ADDR") or None) if request is not None else None


def registrar(tipo, *, usuario=None, nombre_usuario="", request=None, hecho_por=None):
    """Anota un acceso en la bitácora."""
    nombre = nombre_usuario or getattr(usuario, "username", "")
    return Acceso.objects.create(
        tipo=tipo,
        usuario=usuario,
        nombre_usuario=nombre[:150],
        ip=_ip(request),
        hecho_por=hecho_por,
    )


def _ventana():
    return timezone.now() - timedelta(minutes=MINUTOS_DE_BLOQUEO)


def _minutos_que_faltan(bloqueo):
    segundos = (bloqueo + timedelta(minutes=MINUTOS_DE_BLOQUEO) - timezone.now()).total_seconds()
    return max(1, math.ceil(segundos / 60))


def minutos_de_bloqueo(nombre_usuario):
    """0 si ese usuario puede intentar entrar; si está bloqueado, los minutos que le faltan."""
    if not nombre_usuario:
        return 0
    ultimo = (
        Acceso.objects.filter(nombre_usuario__iexact=nombre_usuario, momento__gte=_ventana(),
                              tipo__in=_CORTAN_LA_RACHA)
        .values_list("tipo", "momento")
        .first()
    )
    if ultimo and ultimo[0] == Tipo.BLOQUEO:
        return _minutos_que_faltan(ultimo[1])
    return 0


def bloqueos_activos():
    """{usuario en minúsculas: minutos que le faltan} de todos los que están bloqueados ahora."""
    vistos, bloqueados = set(), {}
    recientes = Acceso.objects.filter(momento__gte=_ventana(), tipo__in=_CORTAN_LA_RACHA)
    for nombre, tipo, momento in recientes.values_list("nombre_usuario", "tipo", "momento"):
        nombre = nombre.lower()
        if nombre in vistos:
            continue  # ya se vio su evento más reciente (vienen del más nuevo al más viejo)
        vistos.add(nombre)
        if tipo == Tipo.BLOQUEO:
            bloqueados[nombre] = _minutos_que_faltan(momento)
    return bloqueados


def intentos_fallidos_seguidos(nombre_usuario):
    """Intentos fallidos de los últimos minutos que cuentan para el bloqueo."""
    recientes = Acceso.objects.filter(
        nombre_usuario__iexact=nombre_usuario, momento__gte=_ventana(),
        tipo__in=(Tipo.FALLIDO, *_CORTAN_LA_RACHA),
    ).values_list("tipo", flat=True)
    seguidos = 0
    for tipo in recientes:
        if tipo != Tipo.FALLIDO:
            break
        seguidos += 1
    return seguidos


def intentos_restantes(nombre_usuario):
    return max(0, INTENTOS_PERMITIDOS - intentos_fallidos_seguidos(nombre_usuario))


# Sin letras ni números que se confundan al dictarlos o copiarlos (O/0, l/1/I)
_LETRAS_CLARAS = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"


def generar_clave_temporal():
    """Contraseña temporal fácil de copiar, como «Kq7mR-x4PtZ»."""
    def trozo():
        return "".join(secrets.choice(_LETRAS_CLARAS) for _ in range(5))
    return f"{trozo()}-{trozo()}"


# ---- Señales: Django avisa cuando alguien entra, sale o se equivoca de contraseña ----

@receiver(user_login_failed)
def al_fallar_la_entrada(sender, credentials, request=None, **kwargs):
    nombre = (credentials.get(Usuario.USERNAME_FIELD) or "").strip()
    if not nombre:
        return
    if minutos_de_bloqueo(nombre):
        registrar(Tipo.INTENTO_BLOQUEADO, nombre_usuario=nombre, request=request,
                  usuario=Usuario.objects.filter(username=nombre).first())
        return
    usuario = Usuario.objects.filter(username=nombre).first()
    registrar(Tipo.FALLIDO, nombre_usuario=nombre, usuario=usuario, request=request)
    if intentos_fallidos_seguidos(nombre) >= INTENTOS_PERMITIDOS:
        registrar(Tipo.BLOQUEO, nombre_usuario=nombre, usuario=usuario, request=request)


@receiver(user_logged_in)
def al_entrar(sender, request, user, **kwargs):
    # ¿Alguien intentó entrar con este usuario desde que entró la última vez?
    # No se cuentan los de esta misma computadora en los últimos minutos (casi seguro fue la persona).
    anterior = Acceso.objects.filter(usuario=user, tipo=Tipo.ENTRADA).values_list("momento", flat=True).first()
    fallidos = Acceso.objects.filter(nombre_usuario__iexact=user.username,
                                     tipo__in=(Tipo.FALLIDO, Tipo.INTENTO_BLOQUEADO))
    if anterior:
        fallidos = fallidos.filter(momento__gt=anterior)
    ip = _ip(request)
    if ip:
        fallidos = fallidos.exclude(ip=ip, momento__gte=_ventana())
    cuantos = fallidos.count()

    registrar(Tipo.ENTRADA, usuario=user, request=request)
    if cuantos and request is not None:
        veces = "1 intento fallido" if cuantos == 1 else f"{cuantos} intentos fallidos"
        messages.warning(
            request,
            f"Desde su último ingreso hubo {veces} de entrar con su usuario. "
            "Si no fue usted, avise al Administrador y cambie su contraseña.",
            fail_silently=True,
        )


@receiver(user_logged_out)
def al_salir(sender, request, user, **kwargs):
    if user is None:
        return
    por_inactividad = getattr(request, "cierre_por_inactividad", False)
    registrar(Tipo.INACTIVIDAD if por_inactividad else Tipo.SALIDA, usuario=user, request=request)
    if not por_inactividad and request is not None:
        messages.success(request, "Cerró su sesión. ¡Hasta pronto!", fail_silently=True)
