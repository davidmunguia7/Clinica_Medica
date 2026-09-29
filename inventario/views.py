from datetime import timedelta

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db.models import F, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from . import services
from .forms import EntradaForm, ProductoForm, SalidaForm
from .models import DIAS_ALERTA_VENCIMIENTO, Lote, Movimiento, Producto

# NOTA: cuando el módulo de login esté listo, activen
# 'django.contrib.auth.middleware.LoginRequiredMiddleware' en settings.py
# y todas estas vistas quedarán protegidas sin tocar este archivo.


def _usuario(request):
    return request.user if request.user.is_authenticated else None


class ProductoListView(ListView):
    model = Producto
    paginate_by = 25

    def get_queryset(self):
        # order_by explícito: el ordering del Meta no se aplica a consultas con Sum()
        qs = Producto.objects.annotate(
            stock_total=Coalesce(Sum("lotes__cantidad_actual"), 0)
        ).order_by("nombre")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(nombre__icontains=q) | Q(codigo__icontains=q))
        if self.request.GET.get("filtro") == "bajo":
            qs = qs.filter(activo=True, stock_total__lte=F("stock_minimo"))
        elif self.request.GET.get("filtro") != "todos":
            qs = qs.filter(activo=True)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        con_stock = Lote.objects.filter(cantidad_actual__gt=0).select_related("producto")
        ctx["lotes_vencidos"] = con_stock.filter(fecha_vencimiento__lt=hoy)
        ctx["lotes_por_vencer"] = con_stock.filter(
            fecha_vencimiento__gte=hoy,
            fecha_vencimiento__lte=hoy + timedelta(days=DIAS_ALERTA_VENCIMIENTO),
        )
        ctx["dias_alerta"] = DIAS_ALERTA_VENCIMIENTO
        ctx["q"] = self.request.GET.get("q", "")
        ctx["filtro"] = self.request.GET.get("filtro", "")
        return ctx


class ProductoDetailView(DetailView):
    model = Producto

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["lotes"] = self.object.lotes.filter(cantidad_actual__gt=0)
        ctx["movimientos"] = self.object.movimientos.select_related("lote", "usuario")[:15]
        return ctx


class ProductoCreateView(SuccessMessageMixin, CreateView):
    model = Producto
    form_class = ProductoForm
    success_message = "Producto «%(nombre)s» creado."

    def get_success_url(self):
        return reverse("inventario:producto_detalle", args=[self.object.pk])


class ProductoUpdateView(SuccessMessageMixin, UpdateView):
    model = Producto
    form_class = ProductoForm
    success_message = "Cambios guardados."

    def get_success_url(self):
        return reverse("inventario:producto_detalle", args=[self.object.pk])


def _movimiento(request, pk, form_class, tipo):
    producto = get_object_or_404(Producto, pk=pk, activo=True)
    form = form_class(request.POST or None)
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        try:
            if tipo == Movimiento.Tipo.ENTRADA:
                services.registrar_entrada(producto=producto, usuario=_usuario(request), **datos)
                messages.success(request, f"Entrada registrada: {datos['cantidad']} {producto.unidad_medida}.")
            else:
                services.registrar_salida(producto=producto, usuario=_usuario(request), **datos)
                messages.success(request, f"Salida registrada: {datos['cantidad']} {producto.unidad_medida}.")
            return redirect("inventario:producto_detalle", pk=producto.pk)
        except ValidationError as e:
            form.add_error(None, e)
    return render(request, "inventario/movimiento_form.html", {
        "producto": producto, "form": form, "tipo": tipo,
        "titulo": "Registrar entrada" if tipo == Movimiento.Tipo.ENTRADA else "Registrar salida",
    })


def registrar_entrada(request, pk):
    return _movimiento(request, pk, EntradaForm, Movimiento.Tipo.ENTRADA)


def registrar_salida(request, pk):
    return _movimiento(request, pk, SalidaForm, Movimiento.Tipo.SALIDA)


class MovimientoListView(ListView):
    model = Movimiento
    paginate_by = 50
    queryset = Movimiento.objects.select_related("producto", "lote", "usuario")
