from django import forms

from .models import Producto

class EstiloMixin:
    """Aplica a todos los campos los componentes de la paleta (theme/static_src/src/styles.css)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "casilla"
            else:
                field.widget.attrs["class"] = "campo"


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
