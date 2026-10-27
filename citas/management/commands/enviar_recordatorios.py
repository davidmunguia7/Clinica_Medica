from django.core.management.base import BaseCommand

from citas.models import MensajeSMS
from citas.recordatorios import citas_por_recordar, enviar_recordatorio
from citas.sms import obtener_backend


class Command(BaseCommand):
    help = (
        "Envía un SMS de recordatorio a los pacientes con cita en las próximas horas "
        "(24 por defecto). Se programa para correr una vez al día."
    )

    def add_arguments(self, parser):
        parser.add_argument("--horas", type=int, default=24, help="Ventana de tiempo (por defecto 24).")
        parser.add_argument(
            "--simular",
            action="store_true",
            help="No envía nada aunque haya un proveedor configurado (solo muestra los mensajes).",
        )

    def handle(self, *args, horas=24, simular=False, **opciones):
        backend = obtener_backend("citas.sms.BackendSimulado" if simular else None)
        citas = list(citas_por_recordar(horas=horas))
        if not citas:
            self.stdout.write("No hay citas por recordar.")
            return
        errores = 0
        for cita in citas:
            mensaje = enviar_recordatorio(cita, backend=backend)
            if mensaje.estado == MensajeSMS.Estado.ERROR:
                errores += 1
                self.stderr.write(f"Error con la cita {cita.pk}: {mensaje.error}")
        enviados = len(citas) - errores
        self.stdout.write(
            self.style.SUCCESS(f"Recordatorios: {enviados} enviados ({backend.nombre}), {errores} con error.")
        )
