from datetime import datetime, time, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone


def _saludo(hora):
    if 5 <= hora < 12:
        return "Buenos días"
    if 12 <= hora < 19:
        return "Buenas tardes"
    return "Buenas noches"


@login_required
def inicio(request):
    """Pantalla de inicio: saludo, búsqueda rápida, resumen y accesos a los módulos."""
    ahora = timezone.localtime()
    contexto = {"saludo": _saludo(ahora.hour), "hoy": ahora.date()}
    zona = timezone.get_current_timezone()
    inicio_dia = timezone.make_aware(datetime.combine(ahora.date(), time.min), zona)
    fin_dia = inicio_dia + timedelta(days=1)

    if request.user.has_perm("pacientes.view_paciente"):
        from pacientes.models import Paciente

        inicio_mes = inicio_dia.replace(day=1)
        contexto.update(
            {
                "total_pacientes": Paciente.objects.filter(activo=True).count(),
                "registrados_hoy": Paciente.objects.filter(
                    fecha_registro__gte=inicio_dia, fecha_registro__lt=fin_dia
                ).count(),
                "registrados_mes": Paciente.objects.filter(fecha_registro__gte=inicio_mes).count(),
                "recientes": Paciente.objects.select_related("historial").order_by("-fecha_registro")[:5],
            }
        )

    if request.user.has_perm("citas.view_cita"):
        from citas.models import Cita

        citas_hoy = list(
            Cita.objects.filter(fecha_hora__gte=inicio_dia, fecha_hora__lt=fin_dia)
            .exclude(estado=Cita.Estado.CANCELADA)
            .select_related("paciente", "medico")
            .order_by("fecha_hora")
        )
        contexto["citas_hoy"] = citas_hoy
        contexto["citas_hoy_pendientes"] = sum(1 for cita in citas_hoy if cita.activa)
    return render(request, "inicio.html", contexto)
