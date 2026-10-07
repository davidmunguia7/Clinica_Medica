"""Lógica de negocio del inventario.

Las vistas (y más adelante otros módulos, p. ej. consultas o recetas)
deben usar estas funciones en lugar de modificar Lote.cantidad_actual
directamente, para que cada cambio de stock quede registrado.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from .models import Lote, Movimiento


@transaction.atomic
def registrar_entrada(*, producto, numero_lote, cantidad, fecha_vencimiento=None, usuario=None, motivo=""):
    if cantidad <= 0:
        raise ValidationError("La cantidad debe ser mayor que cero.")

    lote, creado = Lote.objects.select_for_update().get_or_create(
        producto=producto,
        numero_lote=numero_lote,
        defaults={"fecha_vencimiento": fecha_vencimiento},
    )
    if not creado and fecha_vencimiento and lote.fecha_vencimiento != fecha_vencimiento:
        raise ValidationError(
            f"El lote {numero_lote} ya existe con vencimiento {lote.fecha_vencimiento:%d/%m/%Y}."
        )

    lote.cantidad_actual = F("cantidad_actual") + cantidad
    lote.save(update_fields=["cantidad_actual"])
    lote.refresh_from_db()

    return Movimiento.objects.create(
        producto=producto, lote=lote, tipo=Movimiento.Tipo.ENTRADA,
        cantidad=cantidad, usuario=usuario, motivo=motivo,
    )


@transaction.atomic
def registrar_salida(*, producto, cantidad, usuario=None, motivo=""):
    """Descuenta stock empezando por el lote que vence primero (FEFO).

    Nunca toma lotes vencidos. Devuelve la lista de movimientos creados
    (uno por cada lote del que se sacó producto).
    """
    if cantidad <= 0:
        raise ValidationError("La cantidad debe ser mayor que cero.")

    hoy = timezone.localdate()
    lotes = list(
        Lote.objects.select_for_update()
        .filter(producto=producto, cantidad_actual__gt=0)
        .filter(Q(fecha_vencimiento__isnull=True) | Q(fecha_vencimiento__gte=hoy))
        .order_by(F("fecha_vencimiento").asc(nulls_last=True), "fecha_ingreso")
    )

    disponible = sum(l.cantidad_actual for l in lotes)
    if disponible < cantidad:
        raise ValidationError(
            f"Stock insuficiente de {producto.nombre}: hay {disponible} disponibles "
            f"(sin contar lotes vencidos) y se pidieron {cantidad}."
        )

    movimientos = []
    pendiente = cantidad
    for lote in lotes:
        if pendiente == 0:
            break
        tomar = min(lote.cantidad_actual, pendiente)
        lote.cantidad_actual -= tomar
        lote.save(update_fields=["cantidad_actual"])
        movimientos.append(
            Movimiento.objects.create(
                producto=producto, lote=lote, tipo=Movimiento.Tipo.SALIDA,
                cantidad=tomar, usuario=usuario, motivo=motivo,
            )
        )
        pendiente -= tomar
    return movimientos
