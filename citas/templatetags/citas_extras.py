from django import template
from django.utils import timezone

from citas.recordatorios import hora_en_texto

register = template.Library()


@register.filter
def hora12(valor):
    """Fecha y hora -> '9:30 a. m.' en la hora de El Salvador."""
    if not valor:
        return ""
    return hora_en_texto(timezone.localtime(valor))
