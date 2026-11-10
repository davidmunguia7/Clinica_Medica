"""Ayudas para las pruebas de todos los módulos."""
from django.test import override_settings


def sin_permisos_de_rol():
    """Apaga los permisos del rol mientras dura una prueba.

    Todo usuario tiene un rol, y con él sus permisos. Para probar que una pantalla
    revisa cada permiso (403 sin él, 200 con él) hace falta un usuario que solo
    tenga los que la prueba le da a mano:

        @sin_permisos_de_rol()
        def test_usuario_sin_permiso(self):
            ...
    """
    return override_settings(AUTHENTICATION_BACKENDS=["django.contrib.auth.backends.ModelBackend"])
