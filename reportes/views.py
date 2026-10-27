import csv

from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render

from . import calculos

# Cada parte del reporte se muestra solo a quien puede ver esos datos.
# Ej.: un médico ve pacientes y citas; la administración ve también el dinero.
PERMISOS_POR_SECCION = {
    "pacientes": "pacientes.view_paciente",
    "citas": "citas.view_cita",
    "inventario": "inventario.view_movimiento",
}


def secciones_permitidas(usuario):
    return tuple(s for s, permiso in PERMISOS_POR_SECCION.items() if usuario.has_perm(permiso))


def mensual(request):
    """Reporte de fin de mes: lo que se atendió, se compró y se vendió.

    ?mes=AAAA-MM elige el mes (por defecto, el actual); &formato=csv lo descarga para Excel.
    """
    secciones = secciones_permitidas(request.user)
    if not secciones:
        raise PermissionDenied
    anio, mes = calculos.leer_mes(request.GET.get("mes"))
    reporte = calculos.reporte_mensual(anio, mes, secciones)

    if request.GET.get("formato") == "csv":
        return _como_csv(reporte)
    return render(request, "reportes/mensual.html", {
        "r": reporte,
        "valor_mes": f"{anio:04d}-{mes:02d}",
        "mes_anterior": "{:04d}-{:02d}".format(*calculos.mes_anterior(anio, mes)),
        "mes_siguiente": "{:04d}-{:02d}".format(*calculos.mes_siguiente(anio, mes)),
    })


def _dinero(valor):
    return f"{valor:.2f}"


def _como_csv(r):
    """CSV estándar: coma entre columnas y punto decimal (como se escriben los dólares).

    Lleva BOM UTF-8 para que Excel muestre bien las tildes.
    """
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="reporte-{r["anio"]:04d}-{r["mes"]:02d}.csv"'
    respuesta.write("﻿")
    w = csv.writer(respuesta)
    w.writerow(["Clínica Familiar", "Reporte mensual"])
    w.writerow(["Mes", r["titulo"]])
    w.writerow(["Generado", f"{r['generado']:%d/%m/%Y %H:%M}"])

    if r["comparacion"]:
        w.writerow([])
        w.writerow(["Resumen", "Este mes", r["titulo_anterior"], "Cambio %"])
        for fila in r["comparacion"]:
            convertir = _dinero if fila["dinero"] else str
            w.writerow([fila["nombre"], convertir(fila["actual"]), convertir(fila["anterior"]),
                        "" if fila["variacion"] is None else fila["variacion"]])

    if "pacientes" in r:
        w.writerow([])
        w.writerow(["Pacientes"])
        w.writerow(["Registrados en el mes", r["pacientes"]["nuevos"]])
        w.writerow(["Activos al cierre", r["pacientes"]["activos"]])

    if "citas" in r:
        c = r["citas"]
        w.writerow([])
        w.writerow(["Citas", "Cantidad"])
        for estado in c["por_estado"]:
            w.writerow([estado["nombre"], estado["cantidad"]])
        w.writerow(["Total de citas", c["total"]])
        w.writerow(["Pacientes distintos atendidos", c["pacientes_atendidos"]])
        w.writerow([])
        w.writerow(["Médico", "Citas", "Atendidas"])
        for medico in c["por_medico"]:
            w.writerow([medico["nombre"], medico["total"], medico["atendidas"]])
        w.writerow([])
        w.writerow(["Recordatorios por SMS", "Enviados", "Simulados", "Con error"])
        rec = c["recordatorios"]
        w.writerow(["", rec["enviados"], rec["simulados"], rec["con_error"]])

    if "inventario" in r:
        inv = r["inventario"]
        w.writerow([])
        w.writerow(["Inventario", "Unidades", "Monto ($)", "Sin precio o costo"])
        for fila in inv["conceptos"]:
            w.writerow([fila["nombre"], fila["unidades"], _dinero(fila["monto"]), fila["sin_precio"]])
        m = inv["margen"]
        w.writerow([])
        w.writerow(["Ganancia bruta estimada de las ventas", "Ingreso ($)", "Costo ($)", "Ganancia ($)", "Ganancia %"])
        w.writerow(["", _dinero(m["ingreso"]), _dinero(m["costo"]), _dinero(m["margen"]),
                    "" if m["porcentaje"] is None else m["porcentaje"]])
        w.writerow([])
        w.writerow(["Ventas por categoría", "Unidades", "Monto ($)"])
        for fila in inv["ventas_por_categoria"]:
            w.writerow([fila["categoria"], fila["unidades"], _dinero(fila["monto"])])
        w.writerow([])
        w.writerow(["Productos más vendidos", "Unidades", "Monto ($)"])
        for fila in inv["mas_vendidos"]:
            w.writerow([fila["producto"], fila["unidades"], _dinero(fila["monto"])])
    return respuesta
