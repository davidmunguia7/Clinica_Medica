"""Números del reporte mensual: pacientes atendidos, citas, compras y ventas.

Cada sección se calcula solo si el usuario tiene permiso para verla
(ver PERMISOS_POR_SECCION en views.py).
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dates import MONTHS

from citas.models import Cita, MensajeSMS
from inventario import consultas
from inventario.models import Movimiento
from pacientes.models import Paciente


def nombre_del_mes(anio, mes):
    return f"{MONTHS[mes]} de {anio}".capitalize()


def mes_siguiente(anio, mes):
    return (anio + 1, 1) if mes == 12 else (anio, mes + 1)


def mes_anterior(anio, mes):
    return (anio - 1, 12) if mes == 1 else (anio, mes - 1)


def leer_mes(texto, hoy=None):
    """«2026-10» -> (2026, 10). Si viene vacío o mal escrito, el mes actual."""
    hoy = hoy or timezone.localdate()
    try:
        anio, mes = (int(parte) for parte in (texto or "").split("-"))
        date(anio, mes, 1)
        if not 2000 <= anio <= 2100:
            raise ValueError
    except ValueError:
        return hoy.year, hoy.month
    return anio, mes


def rango_del_mes(anio, mes):
    """Primer instante del mes y primer instante del mes siguiente (hora de El Salvador)."""
    inicio = timezone.make_aware(datetime.combine(date(anio, mes, 1), time.min))
    fin = timezone.make_aware(datetime.combine(date(*mes_siguiente(anio, mes), 1), time.min))
    return inicio, fin


def _variacion(actual, anterior):
    """Cambio en % respecto al mes anterior (None si el mes anterior fue cero)."""
    if not anterior:
        return None
    return round((Decimal(actual) - Decimal(anterior)) * 100 / Decimal(anterior))


# ---------------------------------------------------------------------------
# Secciones
# ---------------------------------------------------------------------------

def seccion_pacientes(inicio, fin):
    return {
        "nuevos": Paciente.objects.filter(fecha_registro__gte=inicio, fecha_registro__lt=fin).count(),
        "activos": Paciente.objects.filter(activo=True, fecha_registro__lt=fin).count(),
    }


def seccion_citas(inicio, fin):
    citas = Cita.objects.filter(fecha_hora__gte=inicio, fecha_hora__lt=fin)
    por_estado = dict(citas.values_list("estado").annotate(n=Count("id")))
    estados = [
        {"clave": clave, "nombre": nombre, "cantidad": por_estado.get(clave, 0)}
        for clave, nombre in Cita.Estado.choices
    ]
    medicos = []
    for fila in (
        citas.values("medico", "medico__first_name", "medico__last_name", "medico__username")
        .annotate(total=Count("id"), atendidas=Count("id", filter=Q(estado=Cita.Estado.ATENDIDA)))
        .order_by("-atendidas", "medico__username")
    ):
        if fila["medico"] is None:
            nombre = "Sin médico asignado"
        else:
            nombre = (f"{fila['medico__first_name']} {fila['medico__last_name']}".strip()
                      or fila["medico__username"])
        medicos.append({"nombre": nombre, "total": fila["total"], "atendidas": fila["atendidas"]})

    mensajes = dict(
        MensajeSMS.objects.filter(creado__gte=inicio, creado__lt=fin)
        .values_list("estado").annotate(n=Count("id"))
    )
    return {
        "total": sum(por_estado.values()),
        "atendidas": por_estado.get(Cita.Estado.ATENDIDA, 0),
        "canceladas": por_estado.get(Cita.Estado.CANCELADA, 0),
        "no_asistio": por_estado.get(Cita.Estado.NO_ASISTIO, 0),
        "pendientes": sum(por_estado.get(e, 0) for e in Cita.ACTIVAS),
        "pacientes_atendidos": citas.filter(estado=Cita.Estado.ATENDIDA)
        .values("paciente").distinct().count(),
        "por_estado": estados,
        "por_medico": medicos,
        "recordatorios": {
            "enviados": mensajes.get(MensajeSMS.Estado.ENVIADO, 0),
            "simulados": mensajes.get(MensajeSMS.Estado.SIMULADO, 0),
            "con_error": mensajes.get(MensajeSMS.Estado.ERROR, 0),
        },
    }


ETIQUETAS_INVENTARIO = [
    ("COMPRA", "Compras", "entrada"),
    ("DONACION", "Donaciones recibidas", "entrada"),
    ("VENTA", "Ventas", "salida"),
    ("USO", "Uso en consulta", "salida"),
    ("MERMA", "Vencido o dañado", "salida"),
    ("AJUSTE_ENT", "Ajustes que sumaron", "entrada"),
    ("AJUSTE_SAL", "Ajustes que restaron", "salida"),
]


def seccion_inventario(inicio, fin):
    movimientos = consultas.movimientos_del_periodo(inicio, fin)
    conceptos = [
        {"clave": clave, "nombre": nombre, "sentido": sentido, **movimientos[clave]}
        for clave, nombre, sentido in ETIQUETAS_INVENTARIO
    ]
    ventas_por_categoria = consultas.ventas_por_categoria(inicio, fin)
    mayor = max((f["monto"] for f in ventas_por_categoria), default=Decimal("0"))
    for fila in ventas_por_categoria:
        fila["porcentaje"] = round(fila["monto"] * 100 / mayor) if mayor else 0
    return {
        "conceptos": conceptos,
        "compras": movimientos[Movimiento.Concepto.COMPRA],
        "ventas": movimientos[Movimiento.Concepto.VENTA],
        "uso": movimientos[Movimiento.Concepto.USO_INTERNO],
        "merma": movimientos[Movimiento.Concepto.MERMA],
        "margen": consultas.margen_de_ventas(inicio, fin),
        "ventas_por_categoria": ventas_por_categoria,
        "mas_vendidos": consultas.mas_vendidos(inicio, fin),
    }


def reporte_mensual(anio, mes, secciones=("pacientes", "citas", "inventario")):
    """Todo el reporte de un mes, con la comparación contra el mes anterior."""
    inicio, fin = rango_del_mes(anio, mes)
    anterior = rango_del_mes(*mes_anterior(anio, mes))
    hoy = timezone.localdate()
    reporte = {
        "anio": anio,
        "mes": mes,
        "titulo": nombre_del_mes(anio, mes),
        "titulo_anterior": nombre_del_mes(*mes_anterior(anio, mes)),
        "desde": date(anio, mes, 1),
        "hasta": date(*mes_siguiente(anio, mes), 1) - timedelta(days=1),
        "en_curso": (anio, mes) == (hoy.year, hoy.month),
        "futuro": (anio, mes) > (hoy.year, hoy.month),
        "generado": timezone.localtime(),
        "comparacion": [],
    }

    if "pacientes" in secciones:
        reporte["pacientes"] = seccion_pacientes(inicio, fin)
        antes = seccion_pacientes(*anterior)
        reporte["comparacion"].append(
            {"nombre": "Pacientes nuevos", "actual": reporte["pacientes"]["nuevos"],
             "anterior": antes["nuevos"], "dinero": False}
        )
    if "citas" in secciones:
        reporte["citas"] = seccion_citas(inicio, fin)
        antes = Cita.objects.filter(
            fecha_hora__gte=anterior[0], fecha_hora__lt=anterior[1], estado=Cita.Estado.ATENDIDA
        ).count()
        reporte["comparacion"].insert(
            0, {"nombre": "Citas atendidas", "actual": reporte["citas"]["atendidas"],
                "anterior": antes, "dinero": False}
        )
    if "inventario" in secciones:
        reporte["inventario"] = seccion_inventario(inicio, fin)
        antes = consultas.movimientos_del_periodo(*anterior)
        for clave, nombre in ((Movimiento.Concepto.COMPRA, "Compras"), (Movimiento.Concepto.VENTA, "Ventas")):
            reporte["comparacion"].append(
                {"nombre": nombre, "actual": reporte["inventario"][nombre.lower()]["monto"],
                 "anterior": antes[clave]["monto"], "dinero": True}
            )
    for fila in reporte["comparacion"]:
        fila["variacion"] = _variacion(fila["actual"], fila["anterior"])
        fila["variacion_abs"] = abs(fila["variacion"]) if fila["variacion"] is not None else None
    return reporte
