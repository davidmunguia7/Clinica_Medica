from django import forms
from django.utils import timezone

from .models import (
    Departamento,
    Distrito,
    HistorialClinico,
    Municipio,
    Paciente,
    normalizar_busqueda,
)
from .validators import normalizar_dui, normalizar_telefono, validar_dui

# Clases definidas en theme/static_src/src/styles.css (paleta oficial de la clínica)
_CAMPO = "campo"
_CAMPO_CON_ERROR = "campo campo-error"
_CASILLA = "casilla"


class EstilosTailwindMixin:
    """Aplica las clases del sistema a cada control y resalta en rojo los que tienen error."""

    def _aplicar_estilos(self):
        errores = self._errors or {}
        for nombre, campo in self.fields.items():
            widget = campo.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = _CASILLA
            else:
                widget.attrs["class"] = _CAMPO_CON_ERROR if nombre in errores else _CAMPO
            if nombre in errores:
                widget.attrs["aria-invalid"] = "true"
            else:
                widget.attrs.pop("aria-invalid", None)

    def full_clean(self):
        super().full_clean()
        self._aplicar_estilos()

    def add_error(self, field, error):
        super().add_error(field, error)
        self._aplicar_estilos()


class SelectConPadre(forms.Select):
    """Select cuyas opciones llevan data-padre="<id>" para filtrarlas en cascada con JS."""

    def __init__(self, *args, campo_padre, **kwargs):
        self.campo_padre = campo_padre
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        opcion = super().create_option(name, value, label, selected, index, subindex, attrs)
        instancia = getattr(value, "instance", None)
        if instancia is not None:
            opcion["attrs"]["data-padre"] = str(getattr(instancia, self.campo_padre))
        return opcion


def _campo_telefono(etiqueta, requerido):
    return forms.CharField(
        label=etiqueta,
        required=requerido,
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "inputmode": "tel",
                "placeholder": "7123-4567",
                "autocomplete": "off",
                "data-formato": "telefono",
            }
        ),
    )


class PacienteForm(EstilosTailwindMixin, forms.ModelForm):
    # Controles de apoyo para elegir el distrito en cascada (no se guardan)
    departamento = forms.ModelChoiceField(
        queryset=Departamento.objects.all(),
        required=False,
        empty_label="Seleccione…",
        widget=forms.Select(attrs={"data-nivel": "departamento"}),
    )
    municipio = forms.ModelChoiceField(
        queryset=Municipio.objects.all(),
        required=False,
        empty_label="Seleccione…",
        widget=SelectConPadre(campo_padre="departamento_id", attrs={"data-nivel": "municipio"}),
    )
    departamento_nacimiento = forms.ModelChoiceField(
        label="Departamento",
        queryset=Departamento.objects.all(),
        required=False,
        empty_label="Seleccione…",
        widget=forms.Select(attrs={"data-nivel": "departamento"}),
    )
    municipio_nacimiento = forms.ModelChoiceField(
        label="Municipio",
        queryset=Municipio.objects.all(),
        required=False,
        empty_label="Seleccione…",
        widget=SelectConPadre(campo_padre="departamento_id", attrs={"data-nivel": "municipio"}),
    )

    numero_documento = forms.CharField(
        label="Número de documento",
        required=False,
        max_length=30,
        widget=forms.TextInput(
            attrs={"autocomplete": "off", "placeholder": "00000000-0", "autofocus": True}
        ),
    )
    telefono = _campo_telefono("Teléfono", requerido=True)
    telefono_alterno = _campo_telefono("Teléfono alterno", requerido=False)
    responsable_telefono = _campo_telefono("Teléfono del responsable", requerido=False)
    responsable_dui = forms.CharField(
        label="DUI del responsable",
        required=False,
        max_length=20,
        widget=forms.TextInput(
            attrs={"placeholder": "00000000-0", "autocomplete": "off", "data-formato": "dui"}
        ),
    )
    consentimiento_datos = forms.BooleanField(
        label=(
            "El paciente (o su responsable) firmó el consentimiento para el tratamiento "
            "de sus datos personales y de salud."
        ),
        help_text=(
            "La Ley para la Protección de Datos Personales (D. L. 144, 2024) pide consentimiento "
            "por escrito y firmado. Puede imprimir la ficha del paciente para que la firme."
        ),
        error_messages={"required": "Marque esta casilla cuando el paciente haya firmado el consentimiento."},
    )
    confirmar_no_duplicado = forms.BooleanField(
        label="Revisé la lista y confirmo que es una persona distinta.",
        required=False,
    )

    class Meta:
        model = Paciente
        fields = [
            "tipo_documento",
            "numero_documento",
            "nombres",
            "primer_apellido",
            "segundo_apellido",
            "apellido_casada",
            "conocido_por",
            "sexo",
            "fecha_nacimiento",
            "nacionalidad",
            "pais_origen",
            "distrito_nacimiento",
            "estado_civil",
            "ocupacion",
            "distrito",
            "area",
            "direccion",
            "punto_referencia",
            "telefono",
            "telefono_alterno",
            "correo",
            "afiliacion",
            "numero_afiliacion",
            "nombre_madre",
            "nombre_padre",
            "responsable_nombre",
            "responsable_parentesco",
            "responsable_dui",
            "responsable_telefono",
            "datos_proporcionados_por",
            "observaciones",
            "consentimiento_datos",
        ]
        widgets = {
            "fecha_nacimiento": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "distrito": SelectConPadre(campo_padre="municipio_id", attrs={"data-nivel": "distrito"}),
            "distrito_nacimiento": SelectConPadre(
                campo_padre="municipio_id", attrs={"data-nivel": "distrito"}
            ),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
            "correo": forms.EmailInput(attrs={"placeholder": "nombre@correo.com"}),
        }
        labels = {
            "distrito_nacimiento": "Distrito",
            "distrito": "Distrito",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.posibles_duplicados = []
        distritos = Distrito.objects.select_related("municipio")
        self.fields["distrito"].queryset = distritos
        self.fields["distrito"].empty_label = "Seleccione…"
        self.fields["distrito_nacimiento"].queryset = distritos
        self.fields["distrito_nacimiento"].empty_label = "Seleccione…"
        self.fields["fecha_nacimiento"].widget.attrs["max"] = timezone.localdate().isoformat()
        for nombre in ("estado_civil", "responsable_parentesco"):
            self.fields[nombre].choices = [("", "Seleccione…")] + list(
                self.fields[nombre].choices
            )[1:]
        for nombre in ("tipo_documento", "sexo", "nacionalidad", "area"):
            opciones = list(self.fields[nombre].choices)
            if opciones and opciones[0][0] == "":
                self.fields[nombre].choices = [("", "Seleccione…")] + opciones[1:]

        # Al editar, preseleccionar departamento y municipio del distrito guardado
        if self.instance.pk:
            if self.instance.distrito_id:
                municipio = self.instance.distrito.municipio
                self.initial.setdefault("municipio", municipio.pk)
                self.initial.setdefault("departamento", municipio.departamento_id)
            if self.instance.distrito_nacimiento_id:
                municipio = self.instance.distrito_nacimiento.municipio
                self.initial.setdefault("municipio_nacimiento", municipio.pk)
                self.initial.setdefault("departamento_nacimiento", municipio.departamento_id)
            # La confirmación de duplicados solo aplica al registrar
            del self.fields["confirmar_no_duplicado"]
        self._aplicar_estilos()

    # --- Limpieza de campos individuales ------------------------------------
    def clean_telefono(self):
        return normalizar_telefono(self.cleaned_data["telefono"])

    def clean_telefono_alterno(self):
        return normalizar_telefono(self.cleaned_data["telefono_alterno"])

    def clean_responsable_telefono(self):
        return normalizar_telefono(self.cleaned_data["responsable_telefono"])

    def clean_responsable_dui(self):
        valor = normalizar_dui(self.cleaned_data["responsable_dui"])
        validar_dui(valor)
        return valor

    # --- Validaciones entre campos ------------------------------------------
    def clean(self):
        datos = super().clean()
        self._validar_ubicacion(datos, "municipio", "distrito")
        self._validar_ubicacion(datos, "municipio_nacimiento", "distrito_nacimiento")
        self._validar_documento_repetido(datos)
        if not self.instance.pk:
            self._buscar_posibles_duplicados(datos)
        return datos

    def _validar_ubicacion(self, datos, campo_municipio, campo_distrito):
        municipio = datos.get(campo_municipio)
        distrito = datos.get(campo_distrito)
        if municipio and distrito and distrito.municipio_id != municipio.pk:
            self.add_error(campo_distrito, "Este distrito no pertenece al municipio seleccionado.")

    def _validar_documento_repetido(self, datos):
        clave = Paciente.calcular_clave_documento(
            datos.get("tipo_documento"), datos.get("numero_documento")
        )
        if not clave:
            return
        existente = (
            Paciente.objects.filter(documento_clave=clave)
            .exclude(pk=self.instance.pk)
            .select_related("historial")
            .first()
        )
        if existente:
            self.add_error(
                "numero_documento",
                f"Ya existe un paciente con este documento: {existente.nombre_completo} "
                f"(expediente {existente.numero_expediente}). Búsquelo en la lista en lugar de "
                "registrarlo de nuevo.",
            )

    def _buscar_posibles_duplicados(self, datos):
        """Norma MINSAL: verificar que el paciente no tenga ya un expediente."""
        fecha = datos.get("fecha_nacimiento")
        nombres = normalizar_busqueda(datos.get("nombres", "")).split()
        apellido = normalizar_busqueda(datos.get("primer_apellido", ""))
        if not (fecha and nombres and apellido):
            return
        candidatos = (
            Paciente.objects.filter(
                fecha_nacimiento=fecha,
                texto_busqueda__contains=apellido,
            )
            .filter(texto_busqueda__contains=nombres[0])
            .select_related("historial")[:5]
        )
        self.posibles_duplicados = list(candidatos)
        if self.posibles_duplicados and not datos.get("confirmar_no_duplicado"):
            self.add_error(
                "confirmar_no_duplicado",
                "Hay pacientes con el mismo nombre y fecha de nacimiento. Revise la lista; si "
                "es otra persona, marque la casilla y guarde de nuevo.",
            )


class HistorialClinicoForm(EstilosTailwindMixin, forms.ModelForm):
    """Antecedentes que se registran al abrir el expediente (HU-01)."""

    class Meta:
        model = HistorialClinico
        fields = [
            "tipo_sangre",
            "alergias",
            "enfermedades_cronicas",
            "medicamentos_actuales",
            "antecedentes_personales",
            "antecedentes_familiares",
        ]
        widgets = {
            "alergias": forms.Textarea(attrs={"rows": 2}),
            "enfermedades_cronicas": forms.Textarea(attrs={"rows": 2}),
            "medicamentos_actuales": forms.Textarea(attrs={"rows": 2}),
            "antecedentes_personales": forms.Textarea(attrs={"rows": 2}),
            "antecedentes_familiares": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("prefix", "historial")
        super().__init__(*args, **kwargs)
        self.fields["tipo_sangre"].choices = [("", "No sabe")] + list(
            self.fields["tipo_sangre"].choices
        )[1:]
        self._aplicar_estilos()

    def guardar_en(self, historial):
        """Copia los datos validados al expediente ya creado y lo guarda."""
        for campo in self._meta.fields:
            setattr(historial, campo, self.cleaned_data[campo])
        historial.save()
        return historial
