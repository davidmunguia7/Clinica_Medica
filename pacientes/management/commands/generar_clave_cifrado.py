from pathlib import Path

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Genera una clave nueva para cifrar los datos sensibles (CLAVE_CIFRADO del .env)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--guardar",
            action="store_true",
            help="La escribe en el archivo .env (solo si todavía no tiene una).",
        )

    def handle(self, *args, guardar=False, **opciones):
        clave = Fernet.generate_key().decode()
        if not guardar:
            self.stdout.write(f"CLAVE_CIFRADO={clave}")
            self.stdout.write("Copie esa línea en su archivo .env.")
            return

        archivo = Path(settings.BASE_DIR) / ".env"
        lineas = archivo.read_text(encoding="utf-8").splitlines() if archivo.exists() else []
        for linea in lineas:
            nombre, _, valor = linea.partition("=")
            if nombre.strip() == "CLAVE_CIFRADO" and valor.strip():
                raise CommandError(
                    "El .env ya tiene CLAVE_CIFRADO. No se cambió para no perder los datos "
                    "que ya están cifrados con ella."
                )
        lineas = [linea for linea in lineas if linea.partition("=")[0].strip() != "CLAVE_CIFRADO"]
        lineas.append(f"CLAVE_CIFRADO={clave}")
        archivo.write_text("\n".join(lineas) + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Clave guardada en {archivo}."))
        self.stdout.write(
            "Guarde una copia en un lugar seguro: sin esta clave no se pueden leer los datos "
            "cifrados. Si ya tenía pacientes registrados, corra: python manage.py recifrar_datos"
        )
