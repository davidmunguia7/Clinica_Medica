from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from . import roles
from .models import Usuario

# El inicio de sesión (entrar, salir, recuperar la contraseña y «Mi cuenta») no va aquí
# todavía: lo trabaja Fer. Al entrar, cada quien llega a «inicio», que ya muestra la
# pantalla de su rol (sistema_clinico/views.py), así que el login no necesita saber de roles.


@login_required
def perfil(request):
    if request.user.rol != Usuario.Rol.RECEPCION:
        raise PermissionDenied
    return render(request, "usuarios/perfil.html")


@permission_required("usuarios.view_usuario", raise_exception=True)
def lista(request):
    """Usuarios del sistema con su rol, y la tabla de qué puede hacer cada rol."""
    usuarios = list(Usuario.objects.order_by("-is_active", "rol", "first_name", "username"))
    return render(request, "usuarios/lista.html", {
        "usuarios": usuarios,
        "roles": [
            {
                "valor": valor,
                "nombre": nombre,
                "descripcion": roles.DESCRIPCIONES[valor],
                "activos": sum(1 for u in usuarios if u.rol == valor and u.is_active),
            }
            for valor, nombre in Usuario.Rol.choices
        ],
        "matriz": roles.matriz(),
    })
