from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from .models import Usuario


@login_required
def perfil(request):
    if request.user.rol != Usuario.Rol.RECEPCION:
        raise PermissionDenied
    return render(request, "usuarios/perfil.html")
