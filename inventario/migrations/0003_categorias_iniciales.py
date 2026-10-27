"""Datos iniciales: categorías del dashboard y concepto de los movimientos viejos.

- Crea las categorías de medicamentos e insumos (se pueden cambiar en el admin).
- Las salidas registradas antes de este cambio quedan como «Venta» sin precio.
  Las entradas viejas ya quedaron como «Compra» por el valor por defecto.
"""
from django.db import migrations

CATEGORIAS = [
    ("Vías respiratorias", "Asma y bronquitis: inhaladores, broncodilatadores, jarabes para la tos."),
    ("Gripe y resfriado", "Antigripales, antihistamínicos y descongestionantes."),
    ("Analgésicos y antipiréticos", "Para el dolor y la fiebre."),
    ("Antiinflamatorios", "Ibuprofeno, naproxeno, diclofenaco y similares."),
    ("Antibióticos", "Se entregan solo con receta médica."),
    ("Gastrointestinales", "Antiácidos, antidiarreicos y sales de rehidratación oral."),
    ("Cardiovasculares", "Presión arterial y corazón."),
    ("Diabetes", "Medicamentos para controlar el azúcar en la sangre."),
    ("Vitaminas y suplementos", "Multivitamínicos, hierro, ácido fólico."),
    ("Dermatológicos", "Cremas y pomadas para la piel."),
    ("Material de curación", "Gasas, vendas, jeringas, guantes, alcohol."),
    ("Otros", "Lo que no entra en otra categoría."),
]


def crear_categorias(apps, schema_editor):
    Categoria = apps.get_model("inventario", "Categoria")
    for orden, (nombre, descripcion) in enumerate(CATEGORIAS, start=1):
        Categoria.objects.get_or_create(
            nombre=nombre, defaults={"descripcion": descripcion, "orden": orden * 10}
        )


def salidas_viejas_como_venta(apps, schema_editor):
    Movimiento = apps.get_model("inventario", "Movimiento")
    Movimiento.objects.filter(tipo="SAL").update(concepto="VENTA")


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0002_categorias_precios"),
    ]

    operations = [
        # Al revertir no se borra nada: la migración 0002 quita la tabla y las columnas.
        migrations.RunPython(crear_categorias, migrations.RunPython.noop),
        migrations.RunPython(salidas_viejas_como_venta, migrations.RunPython.noop),
    ]
