"""Consultas del inventario para el panel por categorías y el reporte mensual.

Solo leen datos (los cambios de stock van en services.py). Se calculan con la base
de datos (Sum, Count) para que funcionen igual con SQL Server y con SQLite.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import DIAS_ALERTA_VENCIMIENTO, Categoria, Lote, Movimiento, Producto

DECIMAL = DecimalField(max_digits=14, decimal_places=2)
# Dinero que representa cada lote en existencia (a costo de compra)
VALOR_LOTE = ExpressionWrapper(F("cantidad_actual") * F("costo_unitario"), output_field=DECIMAL)
# Dinero de cada movimiento (precio o costo por unidad × cantidad)
MONTO = ExpressionWrapper(F("cantidad") * F("precio_unitario"), output_field=DECIMAL)
# Lo que costó lo que se vendió (costo del lote del que salió)
COSTO = ExpressionWrapper(F("cantidad") * F("lote__costo_unitario"), output_field=DECIMAL)


def inicio_del_mes(dia):
    return timezone.make_aware(datetime.combine(dia.replace(day=1), time.min))


def _movimientos(desde, hasta=None):
    qs = Movimiento.objects.filter(fecha__gte=desde)
    return qs.filter(fecha__lt=hasta) if hasta else qs


def _fila_vacia(categoria):
    return {
        "categoria": categoria, "productos": 0, "unidades": 0, "valor": Decimal("0"),
        "bajo_minimo": 0, "lotes_vencidos": 0, "lotes_por_vencer": 0,
        "vendido_unidades": 0, "vendido_monto": Decimal("0"),
    }


def resumen_por_categoria(hoy=None):
    """Existencias, valor, alertas y ventas del mes de cada categoría.

    Devuelve (filas, reabastecer): una fila por categoría (más «Sin categoría» si hay
    productos sin asignar) y la lista de productos activos en o bajo su mínimo,
    empezando por los que más faltan.
    """
    hoy = hoy or timezone.localdate()
    filas = {c.pk: _fila_vacia(c) for c in Categoria.objects.all()}
    filas[None] = _fila_vacia(None)

    productos = (
        Producto.objects.filter(activo=True)
        .select_related("categoria")
        .annotate(stock_total=Coalesce(Sum("lotes__cantidad_actual"), 0))
        .order_by("nombre")
    )
    reabastecer = []
    for producto in productos:
        fila = filas[producto.categoria_id]
        fila["productos"] += 1
        fila["unidades"] += producto.stock_total
        if producto.bajo_minimo:
            fila["bajo_minimo"] += 1
            reabastecer.append(producto)

    limite = hoy + timedelta(days=DIAS_ALERTA_VENCIMIENTO)
    lotes = (
        Lote.objects.filter(producto__activo=True, cantidad_actual__gt=0)
        .values("producto__categoria")
        .annotate(
            valor=Sum(VALOR_LOTE),
            vencidos=Count("id", filter=Q(fecha_vencimiento__lt=hoy)),
            por_vencer=Count("id", filter=Q(fecha_vencimiento__gte=hoy, fecha_vencimiento__lte=limite)),
        )
    )
    for datos in lotes:
        fila = filas[datos["producto__categoria"]]
        fila["valor"] += datos["valor"] or 0
        fila["lotes_vencidos"] += datos["vencidos"]
        fila["lotes_por_vencer"] += datos["por_vencer"]

    ventas = (
        _movimientos(inicio_del_mes(hoy))
        .filter(tipo=Movimiento.Tipo.SALIDA, concepto=Movimiento.Concepto.VENTA)
        .values("producto__categoria")
        .annotate(unidades=Sum("cantidad"), monto=Sum(MONTO))
    )
    for datos in ventas:
        fila = filas[datos["producto__categoria"]]
        fila["vendido_unidades"] += datos["unidades"] or 0
        fila["vendido_monto"] += datos["monto"] or 0

    for fila in filas.values():
        fila["en_orden"] = fila["productos"] - fila["bajo_minimo"]
        fila["porcentaje_en_orden"] = (
            round(fila["en_orden"] * 100 / fila["productos"]) if fila["productos"] else 0
        )

    sin_categoria = filas.pop(None)
    lista = list(filas.values())
    if sin_categoria["productos"]:
        lista.append(sin_categoria)
    reabastecer.sort(key=lambda p: (p.stock_total - p.stock_minimo, p.nombre))
    return lista, reabastecer


def movimientos_del_periodo(desde, hasta=None):
    """Unidades y dinero por concepto (compras, ventas, uso, mermas…) entre dos fechas.

    Las claves son los conceptos (COMPRA, VENTA, USO…); los ajustes se separan en
    AJUSTE_ENT (sumaron) y AJUSTE_SAL (restaron). «sin_precio» cuenta los
    movimientos que no tienen precio o costo registrado.
    """
    claves = [c for c in Movimiento.Concepto.values if c != Movimiento.Concepto.AJUSTE]
    resumen = {
        clave: {"unidades": 0, "monto": Decimal("0"), "sin_precio": 0}
        for clave in claves + ["AJUSTE_ENT", "AJUSTE_SAL"]
    }
    for fila in _movimientos(desde, hasta).values("tipo", "concepto").annotate(
        unidades=Sum("cantidad"),
        monto=Sum(MONTO),
        sin_precio=Count("id", filter=Q(precio_unitario__isnull=True)),
    ):
        clave = fila["concepto"]
        if clave == Movimiento.Concepto.AJUSTE:
            clave = f"AJUSTE_{fila['tipo']}"
        datos = resumen[clave]
        datos["unidades"] += fila["unidades"] or 0
        datos["monto"] += fila["monto"] or 0
        datos["sin_precio"] += fila["sin_precio"]
    return resumen


def _ventas(desde, hasta=None):
    return _movimientos(desde, hasta).filter(
        tipo=Movimiento.Tipo.SALIDA, concepto=Movimiento.Concepto.VENTA
    )


def ventas_por_categoria(desde, hasta=None):
    """[{categoria, unidades, monto}] de mayor a menor venta en dinero."""
    filas = [
        {
            "categoria": fila["producto__categoria__nombre"] or "Sin categoría",
            "unidades": fila["unidades"] or 0,
            "monto": fila["monto"] or Decimal("0"),
        }
        for fila in _ventas(desde, hasta)
        .values("producto__categoria__nombre")
        .annotate(unidades=Sum("cantidad"), monto=Sum(MONTO))
    ]
    return sorted(filas, key=lambda f: (-f["monto"], -f["unidades"], f["categoria"]))


def mas_vendidos(desde, hasta=None, cuantos=5):
    """Los productos con más unidades vendidas en el período."""
    filas = (
        _ventas(desde, hasta)
        .values("producto_id", "producto__nombre")
        .annotate(unidades=Sum("cantidad"), monto=Sum(MONTO))
        .order_by("-unidades", "producto__nombre")[:cuantos]
    )
    return [
        {
            "producto_id": f["producto_id"], "producto": f["producto__nombre"],
            "unidades": f["unidades"] or 0, "monto": f["monto"] or Decimal("0"),
        }
        for f in filas
    ]


def margen_de_ventas(desde, hasta=None):
    """Ganancia bruta estimada: lo vendido menos lo que costó (solo ventas con precio y costo).

    Devuelve {ingreso, costo, margen, porcentaje, incompletas}; «incompletas» cuenta las
    ventas que no entran en el cálculo porque les falta el precio o el costo del lote.
    """
    ventas = _ventas(desde, hasta)
    completas = ventas.filter(precio_unitario__isnull=False, lote__costo_unitario__isnull=False)
    totales = completas.aggregate(ingreso=Sum(MONTO), costo=Sum(COSTO))
    ingreso = totales["ingreso"] or Decimal("0")
    costo = totales["costo"] or Decimal("0")
    margen = ingreso - costo
    return {
        "ingreso": ingreso,
        "costo": costo,
        "margen": margen,
        "porcentaje": round(margen * 100 / ingreso) if ingreso else None,  # entero
        "incompletas": ventas.count() - completas.count(),
    }
