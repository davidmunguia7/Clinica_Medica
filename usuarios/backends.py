"""Permisos según el rol del usuario.

Django pregunta «¿este usuario puede hacer esto?» a cada backend de
AUTHENTICATION_BACKENDS (settings.py). Este responde con la lista de su rol
(usuarios/roles.py). No guarda nada en la base de datos: si a alguien se le
cambia el rol, el cambio vale desde la siguiente pantalla que abra.

Los permisos sueltos que se le den a un usuario en el panel de administración
se suman a los de su rol (de eso se encarga el backend normal de Django).
"""
from django.contrib.auth.backends import BaseBackend

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
