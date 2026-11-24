"""python manage.py preparar_presentacion

Deja lista la base de la presentación: la borra, la vuelve a crear, crea las tablas y carga
los datos de ejemplo. Solo funciona si la base se llama «...presentacion...» (la que usan
los archivos de la carpeta presentacion/), para no borrar nunca la base de trabajo.
"""
import re

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

NOMBRE_VALIDO = re.compile(r"^[A-Za-z0-9_]+$")


def es_base_de_presentacion(nombre):
    return bool(NOMBRE_VALIDO.match(nombre or "")) and "presentacion" in nombre.lower()


class Command(BaseCommand):
    help = (
        "Borra y vuelve a crear la base de la presentación (DB_NAME=clinica_presentacion) con los "
        "datos de ejemplo. Nunca toca otra base."
    )
    requires_system_checks = []  # la base puede no existir todavía

    def add_arguments(self, parser):
        parser.add_argument("--telefono", default="", help="Teléfono de los pacientes (para los SMS).")
        parser.add_argument("--clave", default="", help="Contraseña de los usuarios de ejemplo.")
        parser.add_argument("--sin-preguntar", action="store_true", help="No pide confirmación.")

    def handle(self, *args, telefono="", clave="", sin_preguntar=False, **opciones):
        base = settings.DATABASES["default"]
        nombre = base["NAME"]
        if not es_base_de_presentacion(nombre):
            raise CommandError(
                f"Este comando borra la base completa y la base configurada es «{nombre}». Solo se usa "
                "con la base de la presentación: ejecute presentacion\\preparar_datos.bat."
            )
        if not sin_preguntar:
            respuesta = input(
                f"Se va a borrar la base «{nombre}» y crear de nuevo con datos de ejemplo. ¿Seguir? (s/n): "
            )
            if respuesta.strip().lower() not in ("s", "si", "sí"):
                self.stdout.write("No se hizo nada.")
                return

        self.stdout.write(f"Creando la base «{nombre}»…")
        connections.close_all()
        self._crear_de_cero(base, nombre)
        self.stdout.write("Creando las tablas…")
        call_command("migrate", interactive=False, verbosity=0)
        call_command("cargar_datos_de_ejemplo", telefono=telefono, clave=clave, stdout=self.stdout)

    def _crear_de_cero(self, base, nombre):
        import pyodbc

        opciones = base.get("OPTIONS", {})
        partes = [
            f"DRIVER={{{opciones.get('driver', 'ODBC Driver 17 for SQL Server')}}}",
            f"SERVER={base['HOST']}" + (f",{base['PORT']}" if base.get("PORT") else ""),
            "DATABASE=master",
        ]
        if base.get("USER"):
            partes += [f"UID={base['USER']}", f"PWD={base['PASSWORD']}"]
        else:
            partes.append("Trusted_Connection=yes")
        conexion = pyodbc.connect(";".join(partes), autocommit=True)
        try:
            cursor = conexion.cursor()
            cursor.execute(
                f"IF DB_ID(N'{nombre}') IS NOT NULL BEGIN "
                f"ALTER DATABASE [{nombre}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; "
                f"DROP DATABASE [{nombre}]; END"
            )
            cursor.execute(f"CREATE DATABASE [{nombre}]")
        finally:
            conexion.close()
