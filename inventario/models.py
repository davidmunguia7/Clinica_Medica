from datetime import timedelta

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

DIAS_ALERTA_VENCIMIENTO = 30


class Producto(models.Model):
    class Tipo(models.TextChoices):
        MEDICAMENTO = "MED", "Medicamento"
        INSUMO = "INS", "Insumo médico"
        OTRO = "OTR", "Otro"

    codigo = models.CharField("código", max_length=30, unique=True)
    nombre = models.CharField(max_length=150)
    tipo = models.CharField(max_length=3, choices=Tipo.choices, default=Tipo.MEDICAMENTO)
    presentacion = models.CharField(
        "presentación", max_length=80, blank=True,
        help_text="Ej.: tableta 500 mg, jarabe 120 ml, caja de 100 unidades",
    )
    unidad_medida = models.CharField("unidad de medida", max_length=30, default="unidad")
    stock_minimo = models.PositiveIntegerField("stock mínimo", default=0)
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.codigo})"

    @property
    def stock_actual(self):
        # Si la vista usó ProductoQuerySet.con_stock(), ya viene calculado.
        if hasattr(self, "stock_total"):
            return self.stock_total or 0
        return self.lotes.aggregate(total=Sum("cantidad_actual"))["total"] or 0

    @property
    def bajo_minimo(self):
        return self.stock_actual <= self.stock_minimo


class Lote(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="lotes")
    numero_lote = models.CharField("número de lote", max_length=50)
    fecha_vencimiento = models.DateField("fecha de vencimiento", null=True, blank=True)
    cantidad_actual = models.PositiveIntegerField(default=0)
    fecha_ingreso = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["fecha_vencimiento", "fecha_ingreso"]
        constraints = [
            models.UniqueConstraint(fields=["producto", "numero_lote"], name="lote_unico_por_producto"),
        ]

    def __str__(self):
        return f"{self.producto.nombre} · lote {self.numero_lote}"

    @property
    def vencido(self):
        return bool(self.fecha_vencimiento and self.fecha_vencimiento < timezone.localdate())

    @property
    def por_vencer(self):
        if not self.fecha_vencimiento or self.vencido:
            return False
        return self.fecha_vencimiento <= timezone.localdate() + timedelta(days=DIAS_ALERTA_VENCIMIENTO)


class Movimiento(models.Model):
    class Tipo(models.TextChoices):
        ENTRADA = "ENT", "Entrada"
        SALIDA = "SAL", "Salida"

    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="movimientos")
    lote = models.ForeignKey(Lote, on_delete=models.PROTECT, related_name="movimientos")
    tipo = models.CharField(max_length=3, choices=Tipo.choices)
    cantidad = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    motivo = models.CharField(max_length=200, blank=True)
    fecha = models.DateTimeField(default=timezone.now)
    # Se usa settings.AUTH_USER_MODEL (no auth.User) para que funcione
    # con el modelo de usuario personalizado del módulo de login.
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="movimientos_inventario",
    )

    class Meta:
        ordering = ["-fecha"]
        constraints = [
            models.CheckConstraint(condition=Q(cantidad__gt=0), name="movimiento_cantidad_positiva"),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} de {self.cantidad} · {self.producto.nombre}"
