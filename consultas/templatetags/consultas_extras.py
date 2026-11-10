"""Para mostrar las consultas en pantallas de otros módulos sin tocar sus vistas.

    {% load consultas_extras %}
    {% consultas_del_paciente paciente as consultas %}
"""
from django import template

register = template.Library()


@register.simple_tag
def consultas_del_paciente(paciente, cuantas=10):
    return list(paciente.consultas.select_related("medico").prefetch_related("medicamentos__producto")[:cuantas])


@register.simple_tag
def consulta_de_la_cita(cita):
    from consultas.models import Consulta

    return Consulta.objects.filter(cita=cita).first()
