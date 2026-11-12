from datetime import datetime, time

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.password_validation import password_validators_help_texts
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from . import accesos, roles
from .forms import FormularioCambioDeClave, FormularioDeEntrada
from .models import Acceso, Usuario

# Al entrar, cada quien llega a «inicio», que ya muestra la pantalla de su rol
# (sistema_clinico/views.py), así que el login no necesita saber de roles.


class Entrar(LoginView):
    """/cuentas/entrar/: usuario y contraseña, con bloqueo por intentos fallidos (usuarios/accesos.py)."""

    authentication_form = FormularioDeEntrada
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            **kwargs,
            intentos_permitidos=accesos.INTENTOS_PERMITIDOS,
            minutos_de_bloqueo=accesos.MINUTOS_DE_BLOQUEO,
        )


@login_required
@sensitive_post_parameters()
@never_cache
def cambiar_clave(request):
    """Cada quien cambia su propia contraseña. Es obligatorio si tiene una temporal."""
    obligatorio = request.user.debe_cambiar_clave
    form = FormularioCambioDeClave(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.user.debe_cambiar_clave = False
        usuario = form.save()
        # Sigue con la sesión abierta aquí; las sesiones de otras computadoras se cierran solas
        update_session_auth_hash(request, usuario)
        accesos.registrar(Acceso.Tipo.CAMBIO_CLAVE, usuario=usuario, request=request)
        messages.success(request, "Listo: su contraseña se cambió. Úsela la próxima vez que entre.")
        return redirect("inicio")
    return render(request, "usuarios/cambiar_clave.html", {
        "form": form,
        "obligatorio": obligatorio,
        "requisitos": password_validators_help_texts(),
    })


@require_POST
@never_cache
def sigo_aqui(request):
    """La página avisa que la persona sigue usando el sistema (ver CierrePorInactividad)."""
    return HttpResponse(status=204)


@login_required
def perfil(request):
    if request.user.rol != Usuario.Rol.RECEPCION:
        raise PermissionDenied
    return render(request, "usuarios/perfil.html")


@permission_required("usuarios.view_usuario", raise_exception=True)
def lista(request):
    """Usuarios del sistema con su rol, y la tabla de qué puede hacer cada rol."""
    usuarios = list(Usuario.objects.order_by("-is_active", "rol", "first_name", "username"))
    bloqueados = accesos.bloqueos_activos()
    for u in usuarios:
        u.minutos_de_bloqueo = bloqueados.get(u.username.lower(), 0)
    return render(request, "usuarios/lista.html", {
        "usuarios": usuarios,
        "roles": [
            {
                "valor": valor,
                "nombre": nombre,
                "descripcion": roles.DESCRIPCIONES[valor],
                "activos": sum(1 for u in usuarios if u.rol == valor and u.is_active),
            }
            for valor, nombre in Usuario.Rol.choices
        ],
        "matriz": roles.matriz(),
    })


def _persona_que_administra(request, pk):
    """El usuario sobre el que actúa el Administrador. Las cuentas de superusuario solo las toca otro superusuario."""
    persona = get_object_or_404(Usuario, pk=pk)
    if persona.is_superuser and not request.user.is_superuser:
        raise PermissionDenied
    return persona


@require_POST
@permission_required("usuarios.change_usuario", raise_exception=True)
@never_cache
def restablecer_clave(request, pk):
    """Le da una contraseña temporal a quien olvidó la suya. Al entrar, tendrá que crear la propia."""
    persona = _persona_que_administra(request, pk)
    nombre = persona.get_full_name() or persona.username
    if persona.pk == request.user.pk:
        messages.error(request, "Su propia contraseña la cambia en «Cambiar mi contraseña».")
        return redirect("usuarios:lista")
    if not persona.is_active:
        messages.error(request, f"El usuario de {nombre} está desactivado. Actívelo primero con «Editar».")
        return redirect("usuarios:lista")

    clave = accesos.generar_clave_temporal()
    persona.set_password(clave)
    persona.debe_cambiar_clave = True
    persona.save()  # al cambiar la contraseña se cierran las sesiones que tuviera abiertas
    accesos.registrar(Acceso.Tipo.CLAVE_RESTABLECIDA, usuario=persona, request=request, hecho_por=request.user)
    # Se muestra una sola vez y no se guarda en ningún lado
    return render(request, "usuarios/clave_temporal.html", {"persona": persona, "nombre": nombre, "clave": clave})


@require_POST
@permission_required("usuarios.change_usuario", raise_exception=True)
def desbloquear(request, pk):
    """Quita el bloqueo por intentos fallidos antes de que pasen los minutos."""
    persona = _persona_que_administra(request, pk)
    if accesos.minutos_de_bloqueo(persona.username):
        accesos.registrar(Acceso.Tipo.DESBLOQUEO, usuario=persona, request=request, hecho_por=request.user)
        messages.success(request, f"{persona.get_full_name() or persona.username} ya puede volver a entrar.")
    return redirect("usuarios:lista")


@permission_required("usuarios.view_acceso", raise_exception=True)
def bitacora(request):
    """Bitácora de accesos: quién entró, los intentos fallidos y los bloqueos."""
    registros = Acceso.objects.select_related("usuario", "hecho_por")
    tipo = request.GET.get("tipo", "")
    if tipo in Acceso.Tipo.values:
        registros = registros.filter(tipo=tipo)
    else:
        tipo = ""
    q = request.GET.get("q", "").strip()
    if q:
        registros = registros.filter(
            Q(nombre_usuario__icontains=q) | Q(usuario__first_name__icontains=q) | Q(usuario__last_name__icontains=q)
        )

    hoy = Acceso.objects.filter(momento__gte=timezone.make_aware(datetime.combine(timezone.localdate(), time.min)))
    return render(request, "usuarios/bitacora.html", {
        "pagina": Paginator(registros, 50).get_page(request.GET.get("pagina")),
        "tipos": Acceso.Tipo.choices,
        "tipo": tipo,
        "q": q,
        "entradas_hoy": hoy.filter(tipo=Acceso.Tipo.ENTRADA).count(),
        "fallidos_hoy": hoy.filter(tipo__in=(Acceso.Tipo.FALLIDO, Acceso.Tipo.INTENTO_BLOQUEADO)).count(),
        "bloqueados_ahora": len(accesos.bloqueos_activos()),
    })
