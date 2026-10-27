"""Revisiones que Django corre al iniciar (runserver, migrate, test)."""
from django.conf import settings
from django.core import checks
from django.core.exceptions import ImproperlyConfigured

from sistema_clinico import cifrado


@checks.register(checks.Tags.security)
def revisar_clave_de_cifrado(app_configs, **kwargs):
    try:
        cifrado.fernet()
    except ImproperlyConfigured as error:
        return [checks.Error(str(error), id="pacientes.E001")]
    if not getattr(settings, "CLAVE_CIFRADO", ""):
        return [
            checks.Warning(
                "No hay CLAVE_CIFRADO en el .env: los datos de pacientes se cifran con una "
                "clave de desarrollo que no sirve para producción.",
                hint="Genérela con: python manage.py generar_clave_cifrado --guardar",
                id="pacientes.W001",
            )
        ]
    return []
