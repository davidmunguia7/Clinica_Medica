"""Backends propios: los permisos según el rol y el bloqueo por intentos fallidos.

PermisosPorRol. Django pregunta «¿este usuario puede hacer esto?» a cada backend de
AUTHENTICATION_BACKENDS (settings.py). Este responde con la lista de su rol
(usuarios/roles.py). No guarda nada en la base de datos: si a alguien se le
cambia el rol, el cambio vale desde la siguiente pantalla que abra.

Los permisos sueltos que se le den a un usuario en el panel de administración
se suman a los de su rol (de eso se encarga el backend normal de Django).
"""
from django.contrib.auth.backends import BaseBackend
from django.core.exceptions import PermissionDenied

from .roles import permisos_del_rol


class PermisosPorRol(BaseBackend):
    def get_group_permissions(self, user_obj, obj=None):
        # El rol funciona como un grupo: todos los del mismo rol pueden lo mismo.
        if obj is not None or not getattr(user_obj, "is_active", False):
            return set()
        return set(permisos_del_rol(getattr(user_obj, "rol", None)))

    def has_module_perms(self, user_obj, app_label):
        """¿Puede algo en ese módulo? Lo usa el panel de administración para armar su menú."""
        prefijo = f"{app_label}."
        return any(permiso.startswith(prefijo) for permiso in self.get_group_permissions(user_obj))


class BloqueoPorIntentos:
    """No deja entrar a un usuario bloqueado por intentos fallidos (usuarios/accesos.py).

    Va primero en AUTHENTICATION_BACKENDS: si el usuario está bloqueado, corta antes de que
    se revise la contraseña, así que ni la correcta sirve hasta que pase el bloqueo.
    Vale para todas las entradas: /cuentas/entrar/ y el panel de administración.

    Solo tiene «authenticate», a propósito: sin «get_user» Django nunca lo usa para
    recordar la sesión (de eso se encarga el backend normal) ni le pregunta por permisos.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        from .accesos import minutos_de_bloqueo

        if username and minutos_de_bloqueo(username):
            raise PermissionDenied
        return None
