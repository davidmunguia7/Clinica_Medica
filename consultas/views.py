from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404, redirect, render

from citas.models import Cita
from inventario import services
from inventario.models import Movimiento
from inventario.templatetags.inventario_extras import dinero
from pacientes.models import Paciente, normalizar_busqueda

from . import alergias, entregas
from .forms import ConsultaForm, MedicamentosFormSet
from .models import Consulta, MedicamentoRecetado

Estado = MedicamentoRecetado.Estado


# ---------------------------------------------------------------------------
# Médico: atender y recetar
# ---------------------------------------------------------------------------

def _formulario(request, *, paciente, cita=None, consulta=None):
    """Formulario de la consulta con su receta (para crear o para editar)."""
    nueva = consulta is None
    consulta = consulta or Consulta(paciente=paciente, cita=cita, medico=request.user)
    if nueva and cita is not None:
        consulta.motivo = cita.motivo
    historial = paciente.obtener_historial()
    # Lo ya entregado no se puede cambiar: el inventario ya se descontó
    pendientes = consulta.medicamentos.exclude(estado=Estado.ENTREGADO) if consulta.pk else MedicamentoRecetado.objects.none()
    avisos_alergia = []

    if request.method == "POST":
        form = ConsultaForm(request.POST, instance=consulta)
        formset = MedicamentosFormSet(request.POST, instance=consulta, queryset=pendientes, prefix="medicamentos")
        if form.is_valid() and formset.is_valid():
            avisos_alergia = alergias.coincidencias(historial.alergias, formset.medicamentos_a_guardar())
            if not avisos_alergia or request.POST.get("confirmo_alergias"):
                with transaction.atomic():
                    consulta = form.save()
                    formset.instance = consulta
                    formset.save()
                    if cita is not None and cita.activa:
                        cita.estado = Cita.Estado.ATENDIDA
                        cita.save(update_fields=["estado", "actualizada"])
                por_entregar = consulta.medicamentos.filter(estado=Estado.POR_ENTREGAR).count()
                texto = "Consulta guardada." if nueva else "Cambios guardados."
                if por_entregar:
                    texto += f" Recepción verá {por_entregar} medicamento{'s' if por_entregar != 1 else ''} por entregar."
                messages.success(request, texto)
                return redirect(consulta)
    else:
        form = ConsultaForm(instance=consulta)
        formset = MedicamentosFormSet(instance=consulta, queryset=pendientes, prefix="medicamentos")

    return render(request, "consultas/formulario.html", {
        "form": form,
        "formset": formset,
        "consulta": consulta if consulta.pk else None,
        "paciente": paciente,
        "historial": historial,
        "cita": cita,
        "entregados": consulta.medicamentos.filter(estado=Estado.ENTREGADO).select_related("producto") if consulta.pk else [],
        "avisos_alergia": avisos_alergia,
        "anteriores": paciente.consultas.exclude(pk=consulta.pk).select_related("medico")[:3],
    })


@permission_required("consultas.add_consulta", raise_exception=True)
def atender(request, cita_pk):
    """Atender una cita: abre la consulta con el paciente y el motivo de la cita."""
    cita = get_object_or_404(Cita.objects.select_related("paciente__historial"), pk=cita_pk)
    consulta = Consulta.objects.filter(cita=cita).first()
    if consulta:
        return redirect(consulta)
    if cita.estado in (Cita.Estado.CANCELADA, Cita.Estado.NO_ASISTIO):
        messages.error(request, "Esta cita fue cancelada o el paciente no asistió: no se puede atender.")
        return redirect(cita)
    return _formulario(request, paciente=cita.paciente, cita=cita)


@permission_required("consultas.add_consulta", raise_exception=True)
def nueva(request, paciente_pk):
    """Consulta de un paciente que llegó sin cita."""
    paciente = get_object_or_404(Paciente.objects.select_related("historial"), pk=paciente_pk)
    if not paciente.activo:
        messages.error(request, "El paciente está dado de baja. Reactívelo antes de atenderlo.")
        return redirect(paciente)
    return _formulario(request, paciente=paciente)


@permission_required("consultas.change_consulta", raise_exception=True)
def editar(request, pk):
    consulta = get_object_or_404(Consulta.objects.select_related("paciente__historial", "cita"), pk=pk)
    if consulta.medico_id != request.user.pk and not request.user.is_superuser:
        raise PermissionDenied  # cada médico corrige solo sus consultas
    return _formulario(request, paciente=consulta.paciente, cita=consulta.cita, consulta=consulta)


@permission_required("consultas.view_consulta", raise_exception=True)
def detalle(request, pk):
    consulta = get_object_or_404(
        Consulta.objects.select_related("paciente__historial", "medico", "cita"), pk=pk
    )
    return render(request, "consultas/detalle.html", {
        "consulta": consulta,
        "medicamentos": consulta.medicamentos.select_related("producto", "entregado_por"),
        "puede_editar": request.user.has_perm("consultas.change_consulta")
        and (consulta.medico_id == request.user.pk or request.user.is_superuser),
    })


@permission_required("consultas.view_medicamentorecetado", raise_exception=True)
def receta(request, pk):
    """La receta para imprimir (sin el diagnóstico: solo lo que el paciente necesita)."""
    consulta = get_object_or_404(Consulta.objects.select_related("paciente__historial", "medico"), pk=pk)
    return render(request, "consultas/receta.html", {
        "consulta": consulta,
        "medicamentos": consulta.medicamentos.select_related("producto"),
    })


@permission_required("consultas.view_consulta", raise_exception=True)
def lista(request):
    """Consultas registradas. El médico ve primero las suyas."""
    consultas = Consulta.objects.select_related("paciente__historial", "medico").annotate(
        num_medicamentos=Count("medicamentos")
    )
    es_medico = getattr(request.user, "es_medico", False)
    ver = request.GET.get("ver") or ("mias" if es_medico else "todas")
    if ver == "mias":
        consultas = consultas.filter(medico=request.user)
    q = request.GET.get("q", "").strip()
    if q:
        consultas = consultas.filter(paciente__texto_busqueda__contains=normalizar_busqueda(q))
    pagina = Paginator(consultas, 25).get_page(request.GET.get("pagina"))
    return render(request, "consultas/lista.html", {
        "pagina": pagina, "ver": ver, "q": q, "es_medico": es_medico,
    })


# ---------------------------------------------------------------------------
# Recepción: entregar lo recetado (aquí se descuenta del inventario)
# ---------------------------------------------------------------------------

def consultas_por_entregar():
    pendientes = MedicamentoRecetado.objects.filter(estado=Estado.POR_ENTREGAR).select_related("producto")
    return (
        Consulta.objects.filter(medicamentos__estado=Estado.POR_ENTREGAR)
        .distinct()
        .select_related("paciente__historial", "medico")
        .prefetch_related(Prefetch("medicamentos", queryset=pendientes, to_attr="pendientes"))
        .order_by("fecha")
    )


@permission_required("consultas.entregar_medicamentorecetado", raise_exception=True)
def por_entregar(request):
    return render(request, "consultas/por_entregar.html", {"consultas": consultas_por_entregar()})


ACCIONES = {"entregar", "afuera", "pendiente"}


@permission_required("consultas.entregar_medicamentorecetado", raise_exception=True)
def entregar(request, pk):
    consulta = get_object_or_404(Consulta.objects.select_related("paciente", "medico"), pk=pk)
    pendientes = list(consulta.medicamentos.filter(estado=Estado.POR_ENTREGAR).select_related("producto"))
    for medicamento in pendientes:
        medicamento.disponible = services.disponible(medicamento.producto)
        medicamento.alcanza = medicamento.disponible >= medicamento.cantidad
        # Lo que se le cobra si se entrega como venta (el precio del producto; 0 = sin precio)
        medicamento.precio = medicamento.producto.precio_venta or Decimal("0")
        medicamento.subtotal = medicamento.precio * medicamento.cantidad

    if request.method == "POST":
        concepto = request.POST.get("concepto", "")
        acciones = {m.pk: request.POST.get(f"accion-{m.pk}", "pendiente") for m in pendientes}
        if concepto not in entregas.CONCEPTOS_DE_ENTREGA or not set(acciones.values()) <= ACCIONES:
            messages.error(request, "Revise lo que eligió para cada medicamento.")
        else:
            try:
                with transaction.atomic():
                    entregados = afuera = 0
                    cobrar = Decimal("0")
                    for medicamento in pendientes:
                        if acciones[medicamento.pk] == "entregar":
                            entregas.entregar(medicamento, usuario=request.user, concepto=concepto)
                            entregados += 1
                            cobrar += medicamento.subtotal
                        elif acciones[medicamento.pk] == "afuera":
                            entregas.marcar_afuera(medicamento)
                            afuera += 1
            except ValidationError as error:
                messages.error(request, " ".join(error.messages))
            else:
                partes = []
                if entregados:
                    partes.append(f"{entregados} entregado{'s' if entregados != 1 else ''} y descontado{'s' if entregados != 1 else ''} del inventario")
                if afuera:
                    partes.append(f"{afuera} lo compra afuera")
                texto = ("Listo: " + ", ".join(partes) + ".") if partes else "No se cambió nada."
                if concepto == Movimiento.Concepto.VENTA and cobrar:
                    texto += f" Cobrar al paciente: {dinero(cobrar)}."
                messages.success(request, texto)
                return redirect("consultas:por_entregar")

    venta = Movimiento.Concepto.VENTA
    return render(request, "consultas/entregar.html", {
        "consulta": consulta,
        "pendientes": pendientes,
        "conceptos": entregas.CONCEPTOS_DE_ENTREGA,
        "concepto_inicial": venta,
        "concepto_venta": venta,
        # Total con lo que viene marcado al abrir (lo que alcanza); la pantalla lo recalcula al cambiar
        "total_inicial": sum((m.subtotal for m in pendientes if m.alcanza), Decimal("0")),
    })
