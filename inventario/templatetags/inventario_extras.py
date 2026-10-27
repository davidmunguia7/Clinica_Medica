"""Filtros para mostrar dinero y cantidades.

Se usa formato propio porque el idioma del sistema («es») escribe los decimales
con coma (12,50) y en El Salvador los precios en dólares se escriben con punto:
$1,234.50. Uso en una plantilla:

    {% load inventario_extras %}
    {{ producto.precio_venta|dinero }}   ->  $12.50
    {{ unidades|miles }}                 ->  1,240
"""
from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def dinero(valor, vacio="—"):
    if valor is None or valor == "":
        return vacio
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return vacio
    signo = "−" if numero < 0 else ""
    return f"{signo}${abs(numero):,.2f}"


@register.filter
def miles(valor):
    try:
        return f"{int(valor):,}"
    except (TypeError, ValueError):
        return valor
