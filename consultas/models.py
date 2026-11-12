"""Consultas médicas y recetas (HU-02).

El médico atiende al paciente (desde su cita o sin cita), anota el diagnóstico y
le receta medicamentos. Lo recetado de la farmacia de la clínica queda «por
entregar»: se descuenta del inventario cuando Recepción lo entrega
(consultas/entregas.py), no al recetarlo, porque el paciente puede decidir
comprarlo afuera.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from sistema_clinico.cifrado import CampoCifrado


class Consulta(models.Model):
    paciente = models.ForeignKey(
        "pacientes.Paciente", on_delete=models.PROTECT, related_name="consultas"
    )
    medico = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="médico", on_delete=models.PROTECT,
        related_name="consultas_atendidas",
    )
    cita = models.OneToOneField(
        "citas.Cita", on_delete=models.SET_NULL, null=True, blank=True, related_name="consulta",
        help_text="Vacío si el paciente llegó sin cita.",
    )
    fecha = models.DateTimeField("fecha y hora", default=timezone.now)
    # Todo lo que dice de la salud del paciente se guarda cifrado
    motivo = CampoCifrado("motivo de la consulta", max_length=200)
    sintomas = CampoCifrado("síntomas y hallazgos", blank=True, multilinea=True)
    diagnostico = CampoCifrado("diagnóstico", multilinea=True)
    indicaciones = CampoCifrado(
        "indicaciones y tratamiento", blank=True, multilinea=True,
        help_text="Reposo, dieta, cuidados, cuándo volver…",
    )
    creada = models.DateTimeField(auto_now_add=True)
    actualizada = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha"]
        indexes = [models.Index(fields=["fecha"], name="consulta_fecha")]

    def __str__(self):
        return f"Consulta n.° {self.pk} · {self.paciente} · {timezone.localtime(self.fecha):%d/%m/%Y}"

    def get_absolute_url(self):
        return reverse("consultas:detalle", args=[self.pk])

    @property
    def nombre_medico(self):
        return self.medico.get_full_name() or self.medico.get_username()


class MedicamentoRecetado(models.Model):
    class Estado(models.TextChoices):
        POR_ENTREGAR = "POR_ENTREGAR", "Por entregar"
        ENTREGADO = "ENTREGADO", "Entregado"
        AFUERA = "AFUERA", "Lo compra afuera"

    consulta = models.ForeignKey(Consulta, on_delete=models.CASCADE, related_name="medicamentos")
    producto = models.ForeignKey(
        "inventario.Producto", verbose_name="medicamento de la farmacia", on_delete=models.PROTECT,
        null=True, blank=True, related_name="recetas",
        help_text="Elíjalo si la clínica lo tiene; si no, escriba el nombre.",
    )
    nombre = CampoCifrado(
        "otro medicamento", max_length=150, blank=True,
        help_text="Solo si no está en la farmacia de la clínica (el paciente lo compra afuera).",
    )
    dosis = CampoCifrado(max_length=100, help_text="Ej.: 1 tableta, 5 ml")
    frecuencia = CampoCifrado(max_length=100, help_text="Ej.: cada 8 horas")
    duracion = CampoCifrado("duración", max_length=100, blank=True, help_text="Ej.: por 5 días")
    cantidad = models.PositiveIntegerField(
        "cantidad", default=1, validators=[MinValueValidator(1)],
        help_text="Unidades que se le entregan (tabletas, frascos…).",
    )
    indicaciones = CampoCifrado(max_length=200, blank=True, help_text="Ej.: después de comer")
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.POR_ENTREGAR)
    entregado_en = models.DateTimeField("entregado el", null=True, blank=True, editable=False)
    entregado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        editable=False, related_name="+",
    )
    # Las salidas del inventario que se hicieron al entregarlo (una por lote)
    movimientos = models.ManyToManyField("inventario.Movimiento", blank=True, related_name="recetas")

    class Meta:
        ordering = ["pk"]
        verbose_name = "medicamento recetado"
        verbose_name_plural = "medicamentos recetados"
        permissions = [("entregar_medicamentorecetado", "Puede entregar medicamentos recetados")]

    def __str__(self):
        return f"{self.nombre_medicamento} · {self.dosis} {self.frecuencia}"

    @property
    def nombre_medicamento(self):
        if self.producto_id:
            presentacion = f" ({self.producto.presentacion})" if self.producto.presentacion else ""
            return f"{self.producto.nombre}{presentacion}"
        return self.nombre

    @property
    def es_de_la_farmacia(self):
        return self.producto_id is not None

    def clean(self):
        if not self.producto_id and not (self.nombre or "").strip():
            raise ValidationError("Elija un medicamento de la farmacia o escriba su nombre.")

    def save(self, *args, **kwargs):
        # Lo que la clínica no tiene no se entrega aquí: el paciente lo compra afuera
        if not self.producto_id and self.estado == self.Estado.POR_ENTREGAR:
            self.estado = self.Estado.AFUERA
        super().save(*args, **kwargs)
