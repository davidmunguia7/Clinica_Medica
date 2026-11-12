from django.apps import AppConfig


class UsuariosConfig(AppConfig):
    name = 'usuarios'

    def ready(self):
        # La bitácora de accesos se anota con las señales de entrar, salir y fallar la contraseña
        from . import accesos  # noqa: F401
