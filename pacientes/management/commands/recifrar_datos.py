from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import transaction

from sistema_clinico.cifrado import CampoCifrado


def modelos_con_datos_cifrados():
    """Todos los modelos del sistema que tienen algún CampoCifrado (pacientes, citas, SMS…)."""
    for modelo in apps.get_models():
        campos = [campo.name for campo in modelo._meta.concrete_fields if isinstance(campo, CampoCifrado)]
        if campos:
            yield modelo, campos


class Command(BaseCommand):
    help = (
        "Vuelve a cifrar los datos sensibles con la clave principal (la primera de "
        "CLAVE_CIFRADO) y recalcula las huellas de los documentos. Úselo después de "
        "poner o cambiar la clave."
    )

    def handle(self, *args, **opciones):
        resumen = []
        with transaction.atomic():
            for modelo, campos in modelos_con_datos_cifrados():
                registros = list(modelo.objects.order_by("pk"))
                for registro in registros:
                    # Al guardar se cifra con la clave principal. En Paciente, save()
                    # también recalcula documento_huella y texto_busqueda.
                    registro.save(update_fields=campos)
                resumen.append(f"{len(registros)} {modelo._meta.verbose_name_plural}")
        self.stdout.write(
            self.style.SUCCESS("Listo, cifrado con la clave principal: " + ", ".join(resumen) + ".")
        )
