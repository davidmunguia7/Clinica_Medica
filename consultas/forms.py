from django import forms
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from inventario.models import Producto
from pacientes.forms import EstilosTailwindMixin

from .models import Consulta, MedicamentoRecetado

# Filas en blanco para recetar (las que se dejan vacías no se guardan). En la pantalla se ve una
# sola y las demás aparecen con «+ Agregar otro medicamento» (consultas/formulario.html).
FILAS_EN_BLANCO = 6


class ConsultaForm(EstilosTailwindMixin, forms.ModelForm):
    class Meta:
        model = Consulta
        fields = ["motivo", "sintomas", "diagnostico", "indicaciones"]
        widgets = {
            "motivo": forms.TextInput(attrs={"placeholder": "Ej.: fiebre y dolor de garganta"}),
            "sintomas": forms.Textarea(attrs={"rows": 3}),
            "diagnostico": forms.Textarea(attrs={"rows": 3}),
            "indicaciones": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._aplicar_estilos()


class CampoProducto(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        presentacion = f" · {obj.presentacion}" if obj.presentacion else ""
        return f"{obj.nombre}{presentacion} (hay {obj.existencia} {obj.unidad_medida})"


class MedicamentoForm(EstilosTailwindMixin, forms.ModelForm):
    class Meta:
        model = MedicamentoRecetado
        fields = ["producto", "nombre", "dosis", "frecuencia", "duracion", "cantidad", "indicaciones"]
        field_classes = {"producto": CampoProducto}
        widgets = {
            "dosis": forms.TextInput(attrs={"placeholder": "1 tableta"}),
            "frecuencia": forms.TextInput(attrs={"placeholder": "cada 8 horas"}),
            "duracion": forms.TextInput(attrs={"placeholder": "por 5 días"}),
            "indicaciones": forms.TextInput(attrs={"placeholder": "después de comer"}),
            "cantidad": forms.NumberInput(attrs={"min": 1}),
        }

    def __init__(self, *args, productos=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["producto"].queryset = productos if productos is not None else productos_para_recetar()
        self.fields["producto"].empty_label = "— No está en la farmacia —"
        self._aplicar_estilos()

    def clean(self):
        datos = super().clean()
        if not datos.get("producto") and not (datos.get("nombre") or "").strip():
            raise forms.ValidationError("Elija un medicamento de la farmacia o escriba su nombre.")
        return datos


def productos_para_recetar():
    """Medicamentos e insumos activos, con lo que se puede entregar (para mostrarlo al recetar).

    No cuenta los lotes vencidos: esos no se entregan (inventario.services.disponible).
    """
    hoy = timezone.localdate()
    sin_vencer = Q(lotes__fecha_vencimiento__isnull=True) | Q(lotes__fecha_vencimiento__gte=hoy)
    return (
        Producto.objects.filter(activo=True)
        .annotate(existencia=Coalesce(Sum("lotes__cantidad_actual", filter=sin_vencer), 0))
        .order_by("nombre")
    )


class BaseMedicamentosFormSet(forms.BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._productos = productos_para_recetar()

    def get_form_kwargs(self, index):
        # Una sola consulta de productos para todas las filas
        kwargs = super().get_form_kwargs(index)
        kwargs["productos"] = self._productos
        return kwargs

    def medicamentos_a_guardar(self):
        """Los nombres de lo que se va a recetar (para revisar las alergias)."""
        nombres = []
        for formulario in self.forms:
            if not formulario.has_changed() or self._should_delete_form(formulario):
                continue
            datos = formulario.cleaned_data
            if datos.get("producto"):
                nombres.append(datos["producto"].nombre)
            elif datos.get("nombre"):
                nombres.append(datos["nombre"])
        return nombres


MedicamentosFormSet = forms.inlineformset_factory(
    Consulta, MedicamentoRecetado, form=MedicamentoForm, formset=BaseMedicamentosFormSet,
    extra=FILAS_EN_BLANCO, can_delete=True,
)
