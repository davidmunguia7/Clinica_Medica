"""Arma y envía los recordatorios de cita por SMS."""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import Cita, MensajeSMS
from .sms import obtener_backend, telefono_internacional

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def hora_en_texto(momento):
    """09:30 -> '9:30 a. m.'; 15:00 -> '3:00 p. m.'"""
    hora = momento.hour % 12 or 12
    sufijo = "a. m." if momento.hour < 12 else "p. m."
    return f"{hora}:{momento.minute:02d} {sufijo}"


def telefono_de_contacto(paciente):
    """A los menores se les avisa al teléfono del responsable, si lo tienen."""
    if paciente.es_menor and paciente.responsable_telefono:
        return paciente.responsable_telefono
    return paciente.telefono


def texto_recordatorio(cita):
    local = timezone.localtime(cita.fecha_hora)
    nombre = (cita.paciente.nombres or "").split(" ")[0]
    texto = (
        f"{settings.CLINICA_NOMBRE}: Hola {nombre}, le recordamos su cita el "
        f"{DIAS[local.weekday()]} {local.day}/{local.month} a las {hora_en_texto(local)}"
    )
    if cita.medico:
        texto += f" con {cita.nombre_medico}"
    texto += "."
    if getattr(settings, "CLINICA_TELEFONO", ""):
        texto += f" Si no puede asistir, llame al {settings.CLINICA_TELEFONO}."
    return texto


def enviar_recordatorio(cita, backend=None, usuario=None):
    """Envía (o simula) el recordatorio de una cita y deja registro del mensaje."""
    backend = backend or obtener_backend()
    telefono = telefono_de_contacto(cita.paciente)
    texto = texto_recordatorio(cita)
    if not telefono:
        mensaje = MensajeSMS.objects.create(
            cita=cita, telefono="", texto=texto, estado=MensajeSMS.Estado.ERROR,
            proveedor=getattr(backend, "nombre", ""), error="El paciente no tiene teléfono.",
            enviado_por=usuario,
        )
        return mensaje
    resultado = backend.enviar(telefono_internacional(telefono), texto)
    mensaje = MensajeSMS.objects.create(
        cita=cita,
        telefono=telefono,
        texto=texto,
        estado=resultado.estado,
        proveedor=resultado.proveedor,
        id_externo=resultado.id_externo,
        error=resultado.error,
        enviado_por=usuario,
    )
    if resultado.estado != MensajeSMS.Estado.ERROR:
        cita.recordatorio_enviado = timezone.now()
        cita.save(update_fields=["recordatorio_enviado"])
    return mensaje


def citas_por_recordar(ahora=None, horas=24):
    """Citas activas de las próximas `horas` horas que todavía no tienen recordatorio."""
    ahora = ahora or timezone.now()
    return (
        Cita.objects.filter(
            estado__in=Cita.ACTIVAS,
            recordatorio_enviado__isnull=True,
            fecha_hora__gt=ahora,
            fecha_hora__lte=ahora + timedelta(hours=horas),
            paciente__activo=True,
        )
        .select_related("paciente", "medico")
        .order_by("fecha_hora")
    )
