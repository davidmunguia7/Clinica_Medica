import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import HistorialClinicoForm, PacienteForm
from .models import Paciente, normalizar_busqueda

PACIENTES_POR_PAGINA = 20


def _buscar(consulta, incluir_inactivos=False):
    """Busca por nombre, apellidos, 'conocido por', documento o número de expediente.

    No distingue tildes ni mayúsculas: 'maria pena' encuentra a 'María Peña'.
    """
    pacientes = Paciente.objects.select_related(
        "historial", "distrito__municipio__departamento"
    )
    if not incluir_inactivos:
        pacientes = pacientes.filter(activo=True)
    consulta = consulta.strip()
    if not consulta:
        return pacientes.order_by("-fecha_registro")

    por_texto = Q()
    for palabra in normalizar_busqueda(consulta).split():
        por_texto &= Q(texto_busqueda__contains=palabra)
    filtro = por_texto | Q(historial__numero_expediente__icontains=consulta)
    digitos = re.sub(r"\D", "", consulta)
    if len(digitos) >= 4:
        filtro |= Q(documento_clave__contains=digitos)
    return pacientes.filter(filtro)


@login_required
@permission_required("pacientes.view_paciente", raise_exception=True)
def lista(request):
    consulta = request.GET.get("q", "")
    incluir_inactivos = request.GET.get("inactivos") == "1"
    pagina = Paginator(_buscar(consulta, incluir_inactivos), PACIENTES_POR_PAGINA).get_page(
        request.GET.get("pagina")
    )
    return render(
        request,
        "pacientes/lista.html",
        {"pagina": pagina, "consulta": consulta, "incluir_inactivos": incluir_inactivos},
    )


@login_required
@permission_required("pacientes.add_paciente", raise_exception=True)
def registrar(request):
    if request.method == "POST":
        form = PacienteForm(request.POST)
        form_historial = HistorialClinicoForm(request.POST)
        paciente_valido = form.is_valid()
        historial_valido = form_historial.is_valid()
        if paciente_valido and historial_valido:
            try:
                with transaction.atomic():
                    paciente = form.save(commit=False)
                    paciente.registrado_por = request.user
                    paciente.save()  # crea también el expediente
                    form_historial.guardar_en(paciente.historial)
            except IntegrityError:
                form.add_error(
                    "numero_documento",
                    "Otro usuario acaba de registrar este documento. Búsquelo en la lista.",
                )
            else:
                messages.success(
                    request,
                    f"Paciente registrado. Expediente n.° {paciente.numero_expediente}.",
                )
                return redirect(paciente)
    else:
        form = PacienteForm()
        form_historial = HistorialClinicoForm()
    return render(
        request,
        "pacientes/formulario.html",
        {"form": form, "form_historial": form_historial, "paciente": None},
    )


@login_required
@permission_required("pacientes.view_paciente", raise_exception=True)
def detalle(request, pk):
    paciente = get_object_or_404(
        Paciente.objects.select_related(
            "distrito__municipio__departamento",
            "distrito_nacimiento__municipio__departamento",
            "registrado_por",
        ),
        pk=pk,
    )
    historial = paciente.obtener_historial()
    return render(
        request,
        "pacientes/detalle.html",
        {"paciente": paciente, "historial": historial},
    )


@login_required
@permission_required("pacientes.change_paciente", raise_exception=True)
def editar(request, pk):
    paciente = get_object_or_404(Paciente, pk=pk)
    historial = paciente.obtener_historial()
    if request.method == "POST":
        form = PacienteForm(request.POST, instance=paciente)
        form_historial = HistorialClinicoForm(request.POST, instance=historial)
        paciente_valido = form.is_valid()
        historial_valido = form_historial.is_valid()
        if paciente_valido and historial_valido:
            try:
                with transaction.atomic():
                    form.save()
                    form_historial.save()
            except IntegrityError:
                form.add_error(
                    "numero_documento",
                    "Otro paciente ya tiene este documento. Búsquelo en la lista.",
                )
            else:
                messages.success(request, "Cambios guardados.")
                return redirect(paciente)
    else:
        form = PacienteForm(instance=paciente)
        form_historial = HistorialClinicoForm(instance=historial)
    return render(
        request,
        "pacientes/formulario.html",
        {"form": form, "form_historial": form_historial, "paciente": paciente},
    )


@require_POST
@login_required
@permission_required("pacientes.change_paciente", raise_exception=True)
def cambiar_estado(request, pk):
    """Da de baja o reactiva al paciente. El expediente nunca se borra."""
    paciente = get_object_or_404(Paciente, pk=pk)
    paciente.activo = not paciente.activo
    paciente.save(update_fields=["activo", "fecha_actualizacion"])
    if paciente.activo:
        messages.success(request, "El paciente fue reactivado.")
    else:
        messages.warning(
            request,
            "El paciente fue dado de baja. Su expediente se conserva y puede reactivarlo.",
        )
    return redirect(paciente)
