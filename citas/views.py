from datetime import datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import permission_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from pacientes.models import Paciente

from .forms import CitaForm
from .models import ROL_MEDICO, Cita, MensajeSMS
from .recordatorios import enviar_recordatorio

# Cambios de estado permitidos desde una cita activa (programada o confirmada)
ACCIONES = {
    Cita.Estado.CONFIRMADA: "La cita quedó confirmada.",
    Cita.Estado.ATENDIDA: "La cita quedó marcada como atendida.",
    Cita.Estado.NO_ASISTIO: "Se anotó que el paciente no asistió.",
    Cita.Estado.CANCELADA: "La cita fue cancelada.",
}


def _inicio_del_dia(dia):
    return timezone.make_aware(datetime.combine(dia, time.min), timezone.get_current_timezone())


@permission_required("citas.view_cita", raise_exception=True)
def agenda(request):
    hoy = timezone.localdate()
    fecha = parse_date(request.GET.get("fecha") or "") or hoy
    medico_id = request.GET.get("medico", "")

    citas = Cita.objects.select_related("paciente__historial", "medico")
    if medico_id.isdigit():
        citas = citas.filter(medico_id=medico_id)

    inicio = _inicio_del_dia(fecha)
    del_dia = citas.filter(fecha_hora__gte=inicio, fecha_hora__lt=inicio + timedelta(days=1))

    # Semana de lunes a domingo con el número de citas activas o atendidas por día
    lunes = fecha - timedelta(days=fecha.weekday())
    conteo = {}
    for momento in citas.filter(
        fecha_hora__gte=_inicio_del_dia(lunes),
        fecha_hora__lt=_inicio_del_dia(lunes + timedelta(days=7)),
    ).exclude(estado=Cita.Estado.CANCELADA).values_list("fecha_hora", flat=True):
        dia = timezone.localtime(momento).date()
        conteo[dia] = conteo.get(dia, 0) + 1
    semana = [
        {"dia": lunes + timedelta(days=i), "citas": conteo.get(lunes + timedelta(days=i), 0)}
        for i in range(7)
    ]

    return render(
        request,
        "citas/agenda.html",
        {
            "fecha": fecha,
            "hoy": hoy,
            "anterior": fecha - timedelta(days=1),
            "siguiente": fecha + timedelta(days=1),
            "semana": semana,
            "citas": del_dia,
            "medicos": get_user_model().objects.filter(rol=ROL_MEDICO, is_active=True),
            "medico_id": medico_id,
        },
    )


@permission_required("citas.add_cita", raise_exception=True)
def nueva(request):
    paciente = None
    if request.GET.get("paciente", "").isdigit():
        paciente = get_object_or_404(Paciente, pk=request.GET["paciente"], activo=True)
    if request.method == "POST":
        form = CitaForm(request.POST, paciente=paciente)
        if form.is_valid():
            cita = form.save(commit=False)
            cita.creada_por = request.user
            cita.save()
            messages.success(request, "Cita agendada. El recordatorio se enviará un día antes.")
            return redirect(cita)
    else:
        inicial = {}
        if parse_date(request.GET.get("fecha") or ""):
            inicial["fecha_hora"] = timezone.make_aware(
                datetime.combine(parse_date(request.GET["fecha"]), time(8, 0))
            )
        form = CitaForm(paciente=paciente, initial=inicial)
    return render(request, "citas/formulario.html", {"form": form, "cita": None, "paciente": paciente})


@permission_required("citas.view_cita", raise_exception=True)
def detalle(request, pk):
    cita = get_object_or_404(Cita.objects.select_related("paciente__historial", "medico", "creada_por"), pk=pk)
    return render(
        request,
        "citas/detalle.html",
        {
            "cita": cita,
            "mensajes_sms": cita.mensajes.select_related("enviado_por"),
            "acciones": ACCIONES,
        },
    )


@permission_required("citas.change_cita", raise_exception=True)
def editar(request, pk):
    cita = get_object_or_404(Cita, pk=pk)
    if not cita.activa:
        messages.warning(request, "Solo se pueden cambiar las citas programadas o confirmadas.")
        return redirect(cita)
    if request.method == "POST":
        horario_anterior = cita.fecha_hora
        form = CitaForm(request.POST, instance=cita)
        if form.is_valid():
            cita = form.save(commit=False)
            if cita.fecha_hora != horario_anterior:
                cita.recordatorio_enviado = None  # nueva hora: hay que volver a avisar
            cita.save()
            messages.success(request, "Cambios guardados.")
            return redirect(cita)
    else:
        form = CitaForm(instance=cita)
    return render(request, "citas/formulario.html", {"form": form, "cita": cita, "paciente": cita.paciente})


@require_POST
@permission_required("citas.change_cita", raise_exception=True)
def cambiar_estado(request, pk):
    cita = get_object_or_404(Cita, pk=pk)
    estado = request.POST.get("estado")
    if not cita.activa or estado not in ACCIONES:
        messages.error(request, "Ese cambio no se puede hacer en esta cita.")
        return redirect(cita)
    cita.estado = estado
    cita.save(update_fields=["estado", "actualizada"])
    messages.success(request, ACCIONES[estado])
    return redirect(cita)


@require_POST
@permission_required("citas.change_cita", raise_exception=True)
def recordar(request, pk):
    cita = get_object_or_404(Cita.objects.select_related("paciente", "medico"), pk=pk)
    if not cita.activa:
        messages.error(request, "Solo se recuerdan las citas programadas o confirmadas.")
        return redirect(cita)
    with transaction.atomic():
        mensaje = enviar_recordatorio(cita, usuario=request.user)
    if mensaje.estado == MensajeSMS.Estado.ERROR:
        messages.error(request, f"No se pudo enviar el recordatorio: {mensaje.error}")
    elif mensaje.estado == MensajeSMS.Estado.SIMULADO:
        messages.success(request, f"Recordatorio simulado para {mensaje.telefono} (no salió del sistema).")
    else:
        messages.success(request, f"Recordatorio enviado a {mensaje.telefono}.")
    return redirect(cita)
