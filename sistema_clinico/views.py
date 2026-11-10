from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from citas.models import Cita
from inventario import consultas
from pacientes.models import Paciente
from reportes import calculos
from reportes.views import secciones_permitidas

Usuario = get_user_model()
Rol = Usuario.Rol


def _saludo(hora):
    if 5 <= hora < 12:
        return "Buenos días"
    if 12 <= hora < 19:
        return "Buenas tardes"
    return "Buenas noches"


def _limites_del_dia(ahora):
    """Primer instante de hoy y de mañana (hora de El Salvador)."""
    inicio = timezone.make_aware(datetime.combine(ahora.date(), time.min), timezone.get_current_timezone())
    return inicio, inicio + timedelta(days=1)


def _citas(desde, hasta, **filtros):
    """Citas no canceladas entre dos momentos, en orden de hora."""
    return (
        Cita.objects.filter(fecha_hora__gte=desde, fecha_hora__lt=hasta, **filtros)
        .exclude(estado=Cita.Estado.CANCELADA)
        .select_related("paciente__historial", "medico")
        .order_by("fecha_hora")
    )


def _citas_de_hoy(ahora, **filtros):
    citas = list(_citas(*_limites_del_dia(ahora), **filtros))
    return {"citas_hoy": citas, "citas_hoy_pendientes": sum(1 for cita in citas if cita.activa)}


def _avisos_de_inventario(hoy):
    categorias, reabastecer = consultas.resumen_por_categoria(hoy)
    return {
        "reabastecer": reabastecer[:5],
        "total_reabastecer": len(reabastecer),
        "lotes_vencidos": sum(fila["lotes_vencidos"] for fila in categorias),
        "lotes_por_vencer": sum(fila["lotes_por_vencer"] for fila in categorias),
    }


# ---------------------------------------------------------------------------
# Una pantalla de inicio por rol. Cada función arma solo lo que ese rol necesita
# (y solo si su rol tiene el permiso: ver usuarios/roles.py).
# ---------------------------------------------------------------------------

def _para_recepcion(usuario, ahora):
    """Recepción: la agenda de todos, los pacientes recién registrados y los avisos del inventario."""
    contexto = {}
    if usuario.has_perm("citas.view_cita"):
        contexto.update(_citas_de_hoy(ahora))
    if usuario.has_perm("pacientes.view_paciente"):
        inicio_dia, fin_dia = _limites_del_dia(ahora)
        contexto.update(
            total_pacientes=Paciente.objects.filter(activo=True).count(),
            registrados_hoy=Paciente.objects.filter(
                fecha_registro__gte=inicio_dia, fecha_registro__lt=fin_dia
            ).count(),
            recientes=Paciente.objects.select_related("historial").order_by("-fecha_registro")[:5],
        )
    if usuario.has_perm("inventario.view_producto"):
        contexto["inventario"] = _avisos_de_inventario(ahora.date())
    return contexto


def _para_medico(usuario, ahora):
    """Médico: solo sus citas, el siguiente paciente (con sus alergias) y los próximos días."""
    if not usuario.has_perm("citas.view_cita"):
        return {}
    inicio_dia, fin_dia = _limites_del_dia(ahora)
    contexto = _citas_de_hoy(ahora, medico=usuario)
    pendientes = [cita for cita in contexto["citas_hoy"] if cita.activa]
    proximas = _citas(fin_dia, fin_dia + timedelta(days=7), medico=usuario, estado__in=Cita.ACTIVAS)
    contexto.update(
        mi_agenda=f"{reverse('citas:agenda')}?medico={usuario.pk}",
        citas_hoy_atendidas=sum(1 for cita in contexto["citas_hoy"] if cita.estado == Cita.Estado.ATENDIDA),
        siguiente=pendientes[0] if pendientes else None,
        proximas=proximas[:6],
        total_proximas=proximas.count(),
        citas_sin_medico=_citas(inicio_dia, fin_dia, medico__isnull=True, estado__in=Cita.ACTIVAS).count(),
    )
    return contexto


def _para_administrador(usuario, ahora):
    """Administrador: los números del mes, el equipo con sus roles y los avisos de la clínica."""
    contexto = {}
    secciones = secciones_permitidas(usuario)
    if secciones:
        reporte = calculos.reporte_mensual(ahora.year, ahora.month, secciones)
        contexto.update(resumen_mes=reporte["comparacion"], titulo_mes=reporte["titulo"],
                        titulo_mes_anterior=reporte["titulo_anterior"])
    if usuario.has_perm("citas.view_cita"):
        contexto.update(_citas_de_hoy(ahora))
    if usuario.has_perm("usuarios.view_usuario"):
        usuarios = list(Usuario.objects.filter(is_active=True).order_by("rol", "first_name", "username"))
        contexto.update(
            usuarios=usuarios[:8],
            total_usuarios=len(usuarios),
            usuarios_por_rol=[
                {"valor": valor, "nombre": nombre, "cantidad": sum(1 for u in usuarios if u.rol == valor)}
                for valor, nombre in Rol.choices
            ],
        )
    if usuario.has_perm("inventario.view_producto"):
        contexto["inventario"] = _avisos_de_inventario(ahora.date())
    return contexto


PANTALLAS = {
    Rol.ADMINISTRADOR: ("inicio/administrador.html", _para_administrador),
    Rol.MEDICO: ("inicio/medico.html", _para_medico),
    Rol.RECEPCION: ("inicio/recepcion.html", _para_recepcion),
}


@login_required
def inicio(request):
    """Pantalla de inicio: cada rol ve la suya (Administrador, Médico o Recepción)."""
    ahora = timezone.localtime()
    plantilla, armar = PANTALLAS.get(request.user.rol, PANTALLAS[Rol.RECEPCION])
    contexto = {"saludo": _saludo(ahora.hour), "hoy": ahora.date()}
    contexto.update(armar(request.user, ahora))
    return render(request, plantilla, contexto)
