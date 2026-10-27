from django.apps import AppConfig


class PacientesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pacientes"
    verbose_name = "Registro de pacientes"

    def ready(self):
        from . import checks  # noqa: F401  registra la revisión de CLAVE_CIFRADO
