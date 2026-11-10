"""Entrega de los medicamentos recetados: aquí se descuentan del inventario.

Se usa inventario/services.py (registrar_salida), así que sale primero el lote que
vence antes, nunca un lote vencido, y cada salida queda en el historial de
movimientos con el usuario que entregó y el paciente que recibió.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from inventario import services
from inventario.models import Movimiento

from .models import MedicamentoRecetado

Estado = MedicamentoRecetado.Estado

# Cómo queda la salida en el inventario y en el reporte del mes
CONCEPTOS_DE_ENTREGA = {
    Movimiento.Concepto.VENTA: "Se cobra al paciente (venta)",
    Movimiento.Concepto.USO_INTERNO: "Sin costo (uso en consulta)",
}


@transaction.atomic
def entregar(medicamento, *, usuario, concepto=Movimiento.Concepto.VENTA):
    """Descuenta del inventario la cantidad recetada y marca el medicamento como entregado."""
    medicamento = MedicamentoRecetado.objects.select_for_update().select_related(
        "producto", "consulta__paciente"
    ).get(pk=medicamento.pk)
    if medicamento.estado != Estado.POR_ENTREGAR or not medicamento.producto_id:
        raise ValidationError(f"{medicamento.nombre_medicamento} no está por entregar.")
    if concepto not in CONCEPTOS_DE_ENTREGA:
        raise ValidationError("Elija si se cobra o se entrega sin costo.")
    movimientos = services.registrar_salida(
        producto=medicamento.producto,
        cantidad=medicamento.cantidad,
        usuario=usuario,
        concepto=concepto,
        paciente=medicamento.consulta.paciente,
        motivo=f"Receta de la consulta n.° {medicamento.consulta_id}",
    )
    medicamento.estado = Estado.ENTREGADO
    medicamento.entregado_en = timezone.now()
    medicamento.entregado_por = usuario
    medicamento.save(update_fields=["estado", "entregado_en", "entregado_por"])
    medicamento.movimientos.set(movimientos)
    return medicamento


def marcar_afuera(medicamento):
    """El paciente lo comprará afuera: deja de estar por entregar y no toca el inventario."""
    if medicamento.estado != Estado.POR_ENTREGAR:
        raise ValidationError(f"{medicamento.nombre_medicamento} no está por entregar.")
    medicamento.estado = Estado.AFUERA
    medicamento.save(update_fields=["estado"])
    return medicamento
