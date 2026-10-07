from django import forms

from .models import Producto

INPUT = (
    "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm "
    "focus:border-teal-600 focus:outline-none focus:ring-2 focus:ring-teal-600/30"
)


class EstiloMixin:
    """Aplica las clases de Tailwind a todos los campos del formulario."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "h-4 w-4 accent-teal-700"
            else:
                field.widget.attrs["class"] = INPUT


class ProductoForm(EstiloMixin, forms.ModelForm):
    class Meta:
        model = Producto
        fields = ["codigo", "nombre", "tipo", "presentacion", "unidad_medida", "stock_minimo", "activo"]


class EntradaForm(EstiloMixin, forms.Form):
    numero_lote = forms.CharField(label="Número de lote", max_length=50)
    fecha_vencimiento = forms.DateField(
        label="Fecha de vencimiento", required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Déjalo vacío si el producto no vence.",
    )
    cantidad = forms.IntegerField(min_value=1)
    motivo = forms.CharField(max_length=200, required=False, help_text="Ej.: compra, donación")


class SalidaForm(EstiloMixin, forms.Form):
    cantidad = forms.IntegerField(min_value=1)
    motivo = forms.CharField(max_length=200, required=False, help_text="Ej.: entregado a paciente, dañado")
