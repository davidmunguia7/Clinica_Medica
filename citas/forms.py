from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from pacientes.forms import EstilosTailwindMixin
from pacientes.models import Paciente

from .models import ROL_MEDICO, Cita, nombre_de_usuario


class CampoMedico(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return nombre_de_usuario(obj)


class CampoPaciente(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        expediente = obj.numero_expediente
        return f"{obj.nombre_completo} · Exp. {expediente}" if expediente else obj.nombre_completo


class CitaForm(EstilosTailwindMixin, forms.ModelForm):
    fecha_hora = forms.SplitDateTimeField(
        label="Fecha y hora",
        widget=forms.SplitDateTimeWidget(
            date_attrs={"type": "date", "aria-label": "Fecha de la cita"},
            time_attrs={"type": "time", "step": 900, "aria-label": "Hora de la cita"},
            date_format="%Y-%m-%d",
            time_format="%H:%M",
        ),
        error_messages={"incomplete": "Escriba la fecha y la hora de la cita."},
    )

    class Meta:
        model = Cita
        fields = ["paciente", "medico", "fecha_hora", "duracion_minutos", "motivo", "notas"]
        field_classes = {"paciente": CampoPaciente, "medico": CampoMedico}
        widgets = {
            "motivo": forms.TextInput(attrs={"placeholder": "Ej.: control de presión, fiebre, chequeo general"}),
            "notas": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, paciente=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["paciente"].queryset = Paciente.objects.filter(activo=True).select_related("historial")
        self.fields["paciente"].empty_label = "Seleccione…"
        if paciente is not None:
            self.fields["paciente"].initial = paciente
            self.fields["paciente"].disabled = True
        elif self.instance.pk:
            self.fields["paciente"].disabled = True
        self.fields["medico"].queryset = get_user_model().objects.filter(rol=ROL_MEDICO, is_active=True)
        self.fields["medico"].empty_label = "Sin asignar"
        self.fields["fecha_hora"].widget.widgets[0].attrs["min"] = timezone.localdate().isoformat()
        self._aplicar_estilos()
