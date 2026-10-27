from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db.models import F, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from . import consultas, services
from .forms import EntradaForm, ProductoForm, SalidaForm
from .models import DIAS_ALERTA_VENCIMIENTO, Categoria, Lote, Movimiento, Producto

# Todas las vistas piden iniciar sesión y el permiso de Django que corresponde
# (igual que en pacientes). Sin sesión llevan al login; sin permiso, a la página 403.


def _con_stock_total():
    # order_by explícito: el ordering del Meta no se aplica a consultas con Sum()
    return Producto.objects.annotate(
        stock_total=Coalesce(Sum("lotes__cantidad_actual"), 0)
    ).order_by("nombre")


class ProductoListView(PermissionRequiredMixin, ListView):
    permission_required = "inventario.view_producto"
    model = Producto
    paginate_by = 25

    def get_queryset(self):
        qs = _con_stock_total().select_related("categoria")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(nombre__icontains=q) | Q(codigo__icontains=q))
        categoria = self.request.GET.get("categoria", "")
        if categoria == "sin":
            qs = qs.filter(categoria__isnull=True)
        elif categoria.isdigit():
            qs = qs.filter(categoria_id=int(categoria))
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
        ctx["total_bajo_minimo"] = _con_stock_total().filter(
            activo=True, stock_total__lte=F("stock_minimo")
        ).count()
        ctx["q"] = self.request.GET.get("q", "")
        ctx["filtro"] = self.request.GET.get("filtro", "")
        ctx["categorias"] = Categoria.objects.all()
        ctx["categoria"] = self.request.GET.get("categoria", "")
        return ctx


class ProductoDetailView(PermissionRequiredMixin, DetailView):
    permission_required = "inventario.view_producto"
    model = Producto
    queryset = Producto.objects.select_related("categoria")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["lotes"] = self.object.lotes.filter(cantidad_actual__gt=0)
        ctx["movimientos"] = self.object.movimientos.select_related("lote", "usuario")[:15]
        return ctx


class ProductoCreateView(PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    permission_required = "inventario.add_producto"
    model = Producto
    form_class = ProductoForm
    success_message = "Producto «%(nombre)s» creado."

    def get_initial(self):
        # Desde el panel: «+ Vías respiratorias» abre el formulario con esa categoría elegida
        categoria = self.request.GET.get("categoria", "")
        return {"categoria": categoria} if categoria.isdigit() else {}

    def get_success_url(self):
        return reverse("inventario:producto_detalle", args=[self.object.pk])


class ProductoUpdateView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    permission_required = "inventario.change_producto"
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
                services.registrar_entrada(producto=producto, usuario=request.user, **datos)
                messages.success(request, f"Entrada registrada: {datos['cantidad']} {producto.unidad_medida}.")
            else:
                movimientos = services.registrar_salida(producto=producto, usuario=request.user, **datos)
                messages.success(request, f"Salida registrada: {datos['cantidad']} {producto.unidad_medida}.")
                if any(m.concepto == Movimiento.Concepto.VENTA and m.precio_unitario is None for m in movimientos):
                    messages.warning(
                        request,
                        "La venta quedó sin precio porque el producto no tiene precio de venta. "
                        "Agréguelo con «Editar» para que cuente en el reporte del mes.",
                    )
            return redirect("inventario:producto_detalle", pk=producto.pk)
        except ValidationError as e:
            form.add_error(None, e)
    return render(request, "inventario/movimiento_form.html", {
        "producto": producto, "form": form, "tipo": tipo,
        "titulo": "Registrar entrada" if tipo == Movimiento.Tipo.ENTRADA else "Registrar salida",
    })


@login_required
@permission_required("inventario.add_movimiento", raise_exception=True)
def registrar_entrada(request, pk):
    return _movimiento(request, pk, EntradaForm, Movimiento.Tipo.ENTRADA)


@login_required
@permission_required("inventario.add_movimiento", raise_exception=True)
def registrar_salida(request, pk):
    return _movimiento(request, pk, SalidaForm, Movimiento.Tipo.SALIDA)


class MovimientoListView(PermissionRequiredMixin, ListView):
    permission_required = "inventario.view_movimiento"
    model = Movimiento
    paginate_by = 50
    queryset = Movimiento.objects.select_related("producto", "lote", "usuario")


# ---------------------------------------------------------------------------
# Panel (dashboard) del inventario por categorías
# ---------------------------------------------------------------------------

@login_required
@permission_required("inventario.view_producto", raise_exception=True)
def panel(request):
    hoy = timezone.localdate()
    categorias, reabastecer = consultas.resumen_por_categoria(hoy)
    lotes_sin_costo = Lote.objects.filter(
        producto__activo=True, cantidad_actual__gt=0, costo_unitario__isnull=True
    ).count()
    mes = consultas.movimientos_del_periodo(consultas.inicio_del_mes(hoy))
    return render(request, "inventario/panel.html", {
        "hoy": hoy,
        # Tarjetas solo para las categorías con productos; las vacías se listan aparte
        "categorias": [f for f in categorias if f["productos"]],
        "categorias_vacias": [f["categoria"] for f in categorias if not f["productos"] and f["categoria"]],
        "reabastecer": reabastecer[:10],
        "total_reabastecer": len(reabastecer),
        "total_productos": sum(f["productos"] for f in categorias),
        "total_unidades": sum(f["unidades"] for f in categorias),
        "total_valor": sum((f["valor"] for f in categorias), Decimal("0")),
        "lotes_vencidos": sum(f["lotes_vencidos"] for f in categorias),
        "lotes_por_vencer": sum(f["lotes_por_vencer"] for f in categorias),
        "lotes_sin_costo": lotes_sin_costo,
        "dias_alerta": DIAS_ALERTA_VENCIMIENTO,
        "mes": {
            "compras": mes[Movimiento.Concepto.COMPRA],
            "ventas": mes[Movimiento.Concepto.VENTA],
            "uso": mes[Movimiento.Concepto.USO_INTERNO],
            "merma": mes[Movimiento.Concepto.MERMA],
        },
    })
