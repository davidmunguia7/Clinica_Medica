from decimal import Decimal

from django import forms

from .models import Movimiento, Producto


class EstiloMixin:
    """Aplica a todos los campos los componentes de la paleta (theme/static_src/src/styles.css)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "casilla"
            else:
                field.widget.attrs["class"] = "campo"


def _campo_dinero(etiqueta, ayuda):
    return forms.DecimalField(
        label=etiqueta, required=False, min_value=Decimal("0"),
        max_digits=10, decimal_places=2, help_text=ayuda,
    )


class ProductoForm(EstiloMixin, forms.ModelForm):
    class Meta:
        model = Producto
        fields = [
            "codigo", "nombre", "tipo", "categoria", "presentacion", "unidad_medida",
            "stock_minimo", "precio_venta", "activo",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"].empty_label = "Sin categoría"
        self.fields["precio_venta"].required = False  # vacío = todavía no tiene precio

    def clean_precio_venta(self):
        return self.cleaned_data.get("precio_venta") or Decimal("0")


class EntradaForm(EstiloMixin, forms.Form):
    numero_lote = forms.CharField(label="Número de lote", max_length=50)
    fecha_vencimiento = forms.DateField(
        label="Fecha de vencimiento", required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Déjalo vacío si el producto no vence.",
    )
    cantidad = forms.IntegerField(min_value=1)
    concepto = forms.ChoiceField(
        choices=[(c.value, c.label) for c in Movimiento.CONCEPTOS_ENTRADA],
        initial=Movimiento.Concepto.COMPRA, required=False,
    )
    costo_unitario = _campo_dinero(
        "Costo por unidad ($)", "Lo que se pagó por cada unidad. Sirve para el reporte de compras."
    )
    motivo = forms.CharField(max_length=200, required=False, help_text="Ej.: proveedor, n.° de factura")

    def clean_concepto(self):
        return self.cleaned_data.get("concepto") or Movimiento.Concepto.COMPRA


class SalidaForm(EstiloMixin, forms.Form):
    cantidad = forms.IntegerField(min_value=1)
    concepto = forms.ChoiceField(
        choices=[(c.value, c.label) for c in Movimiento.CONCEPTOS_SALIDA],
        initial=Movimiento.Concepto.VENTA, required=False,
    )
    precio_unitario = _campo_dinero(
        "Precio de venta por unidad ($)",
        "Solo para ventas. Si lo deja vacío se usa el precio del producto.",
    )
    motivo = forms.CharField(max_length=200, required=False, help_text="Ej.: entregado a paciente, dañado")

    def clean_concepto(self):
        return self.cleaned_data.get("concepto") or Movimiento.Concepto.VENTA

    def clean(self):
        datos = super().clean()
        if datos.get("concepto") != Movimiento.Concepto.VENTA:
            datos["precio_unitario"] = None  # no es venta: se usa el costo del lote
        return datos
