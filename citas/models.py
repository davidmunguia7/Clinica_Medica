"""Agenda de citas y recordatorios por mensaje de texto (HU-06)."""
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from sistema_clinico.cifrado import CampoCifrado

ROL_MEDICO = "MEDICO"  # usuarios.Usuario.Rol.MEDICO


def nombre_de_usuario(usuario):
    if usuario is None:
        return ""
    return usuario.get_full_name() or usuario.get_username()


class Cita(models.Model):
    class Estado(models.TextChoices):
        PROGRAMADA = "PROGRAMADA", "Programada"
        CONFIRMADA = "CONFIRMADA", "Confirmada"
        ATENDIDA = "ATENDIDA", "Atendida"
        CANCELADA = "CANCELADA", "Cancelada"
        NO_ASISTIO = "NO_ASISTIO", "No asistió"

    # Estados en los que la cita todavía va a ocurrir (ocupan horario y se recuerdan)
    ACTIVAS = (Estado.PROGRAMADA, Estado.CONFIRMADA)

    class Duracion(models.IntegerChoices):
        QUINCE = 15, "15 minutos"
        VEINTE = 20, "20 minutos"
        TREINTA = 30, "30 minutos"
        CUARENTA_Y_CINCO = 45, "45 minutos"
        SESENTA = 60, "1 hora"

    paciente = models.ForeignKey(
        "pacientes.Paciente", on_delete=models.PROTECT, related_name="citas"
    )
    medico = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="médico",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="citas_como_medico",
        limit_choices_to={"rol": ROL_MEDICO, "is_active": True},
    )
    fecha_hora = models.DateTimeField("fecha y hora")
    duracion_minutos = models.PositiveSmallIntegerField(
        "duración", choices=Duracion.choices, default=Duracion.TREINTA
    )
    # El motivo y las notas son datos de salud: se guardan cifrados
    motivo = CampoCifrado("motivo de la consulta", max_length=200)
    notas = CampoCifrado("notas internas", blank=True, multilinea=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PROGRAMADA)
    recordatorio_enviado = models.DateTimeField(
        "recordatorio enviado", null=True, blank=True, editable=False
    )
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="citas_creadas",
    )
    creada = models.DateTimeField(auto_now_add=True)
    actualizada = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["fecha_hora"]
        indexes = [
            models.Index(fields=["fecha_hora"], name="cita_fecha_hora"),
            models.Index(fields=["estado", "fecha_hora"], name="cita_estado_fecha"),
        ]

    def __str__(self):
        local = timezone.localtime(self.fecha_hora)
        return f"{self.paciente} · {local:%d/%m/%Y %H:%M}"

    def get_absolute_url(self):
        return reverse("citas:detalle", args=[self.pk])

    @property
    def fin(self):
        return self.fecha_hora + timedelta(minutes=self.duracion_minutos)

    @property
    def activa(self):
        return self.estado in self.ACTIVAS

    @property
    def nombre_medico(self):
        return nombre_de_usuario(self.medico)

    def clean(self):
        errores = {}
        if self.fecha_hora and self.activa:
            cambio_horario = True
            if self.pk:
                anterior = Cita.objects.filter(pk=self.pk).values_list("fecha_hora", flat=True).first()
                cambio_horario = anterior != self.fecha_hora
            if cambio_horario and self.fecha_hora < timezone.now():
                errores["fecha_hora"] = "La cita debe ser en una fecha y hora que todavía no ha pasado."
            else:
                otra = self.choque_de_horario()
                if otra:
                    hora = timezone.localtime(otra.fecha_hora)
                    errores["fecha_hora"] = (
                        f"El médico ya tiene una cita a esa hora ({otra.paciente}, {hora:%H:%M}). "
                        "Elija otra hora."
                    )
        if self.paciente_id and not self.paciente.activo:
            errores["paciente"] = "El paciente está dado de baja. Reactívelo antes de agendarle una cita."
        if errores:
            raise ValidationError(errores)

    def choque_de_horario(self):
        """Otra cita activa del mismo médico que se cruza con esta (o None)."""
        if not (self.medico_id and self.fecha_hora):
            return None
        mismo_dia = Cita.objects.filter(
            medico_id=self.medico_id,
            estado__in=self.ACTIVAS,
            fecha_hora__gt=self.fecha_hora - timedelta(hours=2),
            fecha_hora__lt=self.fin,
        ).exclude(pk=self.pk)
        for otra in mismo_dia.select_related("paciente"):
            if otra.fecha_hora < self.fin and self.fecha_hora < otra.fin:
                return otra
        return None


class MensajeSMS(models.Model):
    """Cada recordatorio enviado (o simulado), para saber qué se le avisó a quién."""

    class Estado(models.TextChoices):
        SIMULADO = "SIMULADO", "Simulado (no salió del sistema)"
        ENVIADO = "ENVIADO", "Enviado"
        ERROR = "ERROR", "Error al enviar"

    cita = models.ForeignKey(Cita, on_delete=models.CASCADE, related_name="mensajes")
    telefono = CampoCifrado("teléfono", max_length=20)
    texto = CampoCifrado(multilinea=True)
    estado = models.CharField(max_length=10, choices=Estado.choices)
    proveedor = models.CharField(max_length=30)
    id_externo = models.CharField("identificador del proveedor", max_length=100, blank=True)
    error = models.TextField(blank=True)
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Vacío si lo envió el recordatorio automático.",
    )
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado"]
        verbose_name = "mensaje SMS"
        verbose_name_plural = "mensajes SMS"

    def __str__(self):
        return f"{self.get_estado_display()} · {self.cita}"
