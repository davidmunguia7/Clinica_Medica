"""python manage.py cargar_datos_de_ejemplo [--telefono 7123-4567] [--clave ...]

Carga los datos de ejemplo (consultas/datos_de_ejemplo.py) en una base sin pacientes y deja
los usuarios y la contraseña en credenciales_presentacion.txt (ese archivo no se sube a GitHub).
"""
import os
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from consultas import datos_de_ejemplo
from pacientes.models import Paciente
from pacientes.validators import normalizar_telefono, validar_telefono

ARCHIVO_CREDENCIALES = settings.BASE_DIR / "credenciales_presentacion.txt"
PALABRAS = ["Ceiba", "Lempa", "Izalco", "Torogoz", "Conacaste", "Guazapa", "Jiboa", "Coatepeque"]
NOMBRES_DE_ROL = {"ADMIN": "Administrador", "MEDICO": "Médico", "RECEPCION": "Recepción"}


def clave_guardada(archivo):
    """La contraseña que quedó en el archivo la vez anterior (para no cambiarla en cada carga)."""
    try:
        lineas = archivo.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for linea in lineas:
        if linea.startswith("Contraseña"):
            return linea.split(":", 1)[1].strip()
    return ""


def guardar_credenciales(archivo, clave):
    filas = "\n".join(
        f"  {usuario:<15} {NOMBRES_DE_ROL[rol]:<14} {nombre} {apellido}"
        for usuario, nombre, apellido, rol in datos_de_ejemplo.USUARIOS
    )
    archivo.write_text(
        "Clínica Familiar · Usuarios de los datos de ejemplo (todo es inventado)\n\n"
        f"Contraseña (la misma para todos): {clave}\n\n"
        f"  {'Usuario':<15} {'Rol':<14} Nombre\n{filas}\n\n"
        "Este archivo no se sube a GitHub. La dirección pública la muestra presentacion\\encender.bat.\n",
        encoding="utf-8",
    )


class Command(BaseCommand):
    help = (
        "Carga datos de ejemplo inventados para probar o presentar el sistema: usuarios de los tres "
        "roles, pacientes, inventario, citas, consultas y recetas. Solo funciona en una base sin pacientes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--telefono",
            default="",
            help="Teléfono de todos los pacientes de ejemplo, para que los recordatorios por SMS lleguen "
                 "ahí. Si no se da, se usa PRESENTACION_TELEFONO del .env o teléfonos fijos inventados.",
        )
        parser.add_argument(
            "--clave",
            default="",
            help="Contraseña de los usuarios de ejemplo. Si no se da, se usa la de la vez anterior o se inventa una.",
        )

    def handle(self, *args, telefono="", clave="", **opciones):
        if Paciente.objects.exists():
            raise CommandError(
                "Esta base ya tiene pacientes. Los datos de ejemplo van en una base nueva: use "
                "«python manage.py preparar_presentacion» (ver docs/presentacion.md)."
            )
        if get_user_model().objects.filter(username__in=datos_de_ejemplo.NOMBRES_DE_USUARIO).exists():
            raise CommandError("Los usuarios de ejemplo ya existen en esta base.")

        telefono = normalizar_telefono(telefono or os.getenv("PRESENTACION_TELEFONO", ""))
        try:
            validar_telefono(telefono)
        except ValidationError as error:
            raise CommandError(f"Teléfono no válido: {error.messages[0]}")
        clave = clave or clave_guardada(ARCHIVO_CREDENCIALES) or (
            f"{secrets.choice(PALABRAS)}-{secrets.randbelow(9000) + 1000}"
        )

        resumen = datos_de_ejemplo.cargar(clave=clave, telefono=telefono)
        guardar_credenciales(ARCHIVO_CREDENCIALES, clave)

        self.stdout.write(self.style.SUCCESS("Datos de ejemplo cargados:"))
        self.stdout.write(
            f"  {resumen['usuarios']} usuarios, {resumen['pacientes']} pacientes, "
            f"{resumen['productos']} productos y {resumen['consultas']} consultas.\n"
            f"  Citas de hoy: {resumen['citas_hoy']} · próximas: {resumen['citas_proximas']} · "
            f"medicamentos por entregar: {resumen['por_entregar']}."
        )
        if telefono:
            self.stdout.write(f"  Los recordatorios por SMS de los pacientes van al {telefono}.")
        self.stdout.write(f"  Usuarios y contraseña: {ARCHIVO_CREDENCIALES}")
