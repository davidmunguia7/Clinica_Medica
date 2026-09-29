"""Registro de pacientes (HU-01).

Los campos siguen lo que pide el MINSAL para inscribir e identificar a un
paciente en un establecimiento de salud:

- "Procedimiento para la inscripción en el establecimiento de salud (registro
  e identificación)", Acuerdo n.° 2454-BIS, 29 de septiembre de 2025.
- "Norma técnica del expediente clínico", Acuerdo n.° 1616, 30 de mayo de 2024
  (número único por paciente, datos del responsable, quién dio los datos,
  quién los tomó y fecha/hora del registro).

El domicilio usa la división territorial vigente desde el 1 de mayo de 2024:
14 departamentos, 44 municipios y 262 distritos.
"""
import re
import unicodedata

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone

from .validators import (
    normalizar_dui,
    normalizar_telefono,
    solo_digitos,
    validar_dui,
    validar_telefono,
)

MAYORIA_DE_EDAD = 18
EDAD_MAXIMA = 120


def normalizar_busqueda(texto):
    """Minúsculas, sin tildes ni signos: 'María  Peña' -> 'maria pena'."""
    descompuesto = unicodedata.normalize("NFKD", texto or "")
    sin_tildes = "".join(c for c in descompuesto if not unicodedata.combining(c))
    limpio = re.sub(r"[^0-9A-Za-z\s-]", " ", sin_tildes).lower()
    return " ".join(limpio.split())


def calcular_edad(fecha_nacimiento, hoy=None):
    """Edad en años cumplidos."""
    hoy = hoy or timezone.localdate()
    cumplio = (hoy.month, hoy.day) >= (fecha_nacimiento.month, fecha_nacimiento.day)
    return hoy.year - fecha_nacimiento.year - (0 if cumplio else 1)


def edad_en_texto(fecha_nacimiento, hoy=None):
    """Edad legible. A los menores de 2 años se les muestra en meses (uso pediátrico)."""
    hoy = hoy or timezone.localdate()
    meses = (hoy.year - fecha_nacimiento.year) * 12 + (hoy.month - fecha_nacimiento.month)
    if hoy.day < fecha_nacimiento.day:
        meses -= 1
    if meses < 1:
        dias = (hoy - fecha_nacimiento).days
        return f"{dias} día" if dias == 1 else f"{dias} días"
    if meses < 24:
        anios, resto = divmod(meses, 12)
        texto_meses = f"{resto} mes" if resto == 1 else f"{resto} meses"
        if anios == 0:
            return texto_meses
        return "1 año" if resto == 0 else f"1 año {texto_meses}"
    return f"{meses // 12} años"


# ---------------------------------------------------------------------------
# Catálogos de la división territorial (se cargan con la migración 0002)
# ---------------------------------------------------------------------------


class Departamento(models.Model):
    codigo = models.CharField("código ISO 3166-2", max_length=5, unique=True)
    nombre = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Municipio(models.Model):
    departamento = models.ForeignKey(
        Departamento, on_delete=models.PROTECT, related_name="municipios"
    )
    nombre = models.CharField(max_length=60, unique=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Distrito(models.Model):
    municipio = models.ForeignKey(
        Municipio, on_delete=models.PROTECT, related_name="distritos"
    )
    nombre = models.CharField(max_length=60)

    class Meta:
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["municipio", "nombre"], name="distrito_unico_por_municipio"
            )
        ]

    def __str__(self):
        return f"{self.nombre} ({self.municipio.nombre})"


# ---------------------------------------------------------------------------
# Paciente: ficha de identificación
# ---------------------------------------------------------------------------


class Paciente(models.Model):
    class TipoDocumento(models.TextChoices):
        DUI = "DUI", "DUI"
        NUI = "NUI", "NUI (Número Único de Identidad, nacidos desde 2023)"
        CUN = "CUN", "CUN (Código Único de Nacimiento)"
        PARTIDA = "PARTIDA", "Partida de nacimiento"
        MINORIDAD = "MINORIDAD", "Carné de minoridad"
        PASAPORTE = "PASAPORTE", "Pasaporte"
        RESIDENTE = "RESIDENTE", "Carné de residente"
        NINGUNO = "NINGUNO", "No presenta documento"

    class Sexo(models.TextChoices):
        FEMENINO = "F", "Femenino"
        MASCULINO = "M", "Masculino"

    class Nacionalidad(models.TextChoices):
        SALVADORENA = "SV", "Salvadoreña"
        EXTRANJERA = "EX", "Extranjera"

    class EstadoCivil(models.TextChoices):
        SOLTERO = "SOLTERO", "Soltero(a)"
        CASADO = "CASADO", "Casado(a)"
        ACOMPANADO = "ACOMPANADO", "Acompañado(a)"
        DIVORCIADO = "DIVORCIADO", "Divorciado(a)"
        VIUDO = "VIUDO", "Viudo(a)"

    class Area(models.TextChoices):
        URBANA = "U", "Urbana"
        RURAL = "R", "Rural"

    class Afiliacion(models.TextChoices):
        NINGUNA = "NINGUNA", "Ninguna (particular)"
        ISSS = "ISSS", "ISSS"
        ISBM = "ISBM", "Bienestar Magisterial (ISBM)"
        COSAM = "COSAM", "Sanidad Militar (COSAM)"
        PRIVADO = "PRIVADO", "Seguro médico privado"
        OTRA = "OTRA", "Otra"

    class Parentesco(models.TextChoices):
        MADRE = "MADRE", "Madre"
        PADRE = "PADRE", "Padre"
        CONYUGE = "CONYUGE", "Esposo(a) / compañero(a) de vida"
        HIJO = "HIJO", "Hijo(a)"
        HERMANO = "HERMANO", "Hermano(a)"
        ABUELO = "ABUELO", "Abuelo(a)"
        TIO = "TIO", "Tío(a)"
        TUTOR = "TUTOR", "Tutor(a) legal"
        OTRO = "OTRO", "Otro"

    # --- Identificación -----------------------------------------------------
    tipo_documento = models.CharField(
        "tipo de documento",
        max_length=10,
        choices=TipoDocumento.choices,
        default=TipoDocumento.DUI,
    )
    numero_documento = models.CharField("número de documento", max_length=30, blank=True)
    # Documento normalizado ("DUI:012345678"). Es único para que un mismo
    # documento no se registre dos veces; queda vacío (NULL) si no hay documento.
    documento_clave = models.CharField(
        max_length=45, unique=True, null=True, blank=True, editable=False
    )
    nombres = models.CharField(max_length=100)
    primer_apellido = models.CharField("primer apellido", max_length=60)
    segundo_apellido = models.CharField("segundo apellido", max_length=60, blank=True)
    apellido_casada = models.CharField(
        "apellido de casada",
        max_length=60,
        blank=True,
        help_text="Solo el apellido, sin «de». Ej.: Pérez.",
    )
    conocido_por = models.CharField("conocido(a) por", max_length=100, blank=True)

    # --- Datos personales ---------------------------------------------------
    sexo = models.CharField(max_length=1, choices=Sexo.choices)
    fecha_nacimiento = models.DateField("fecha de nacimiento")
    nacionalidad = models.CharField(
        max_length=2, choices=Nacionalidad.choices, default=Nacionalidad.SALVADORENA
    )
    pais_origen = models.CharField("país de origen", max_length=60, blank=True)
    distrito_nacimiento = models.ForeignKey(
        Distrito,
        verbose_name="distrito de nacimiento",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    estado_civil = models.CharField(
        "estado civil", max_length=10, choices=EstadoCivil.choices, blank=True
    )
    ocupacion = models.CharField("ocupación", max_length=100, blank=True)

    # --- Domicilio actual ---------------------------------------------------
    distrito = models.ForeignKey(
        Distrito, on_delete=models.PROTECT, related_name="pacientes"
    )
    area = models.CharField("área", max_length=1, choices=Area.choices)
    direccion = models.CharField(
        "dirección",
        max_length=255,
        help_text="Colonia, barrio, cantón o caserío; calle o pasaje; número de casa.",
    )
    punto_referencia = models.CharField(
        "punto de referencia",
        max_length=150,
        blank=True,
        help_text="Ej.: frente a la iglesia, a una cuadra del parque.",
    )

    # --- Contacto -----------------------------------------------------------
    telefono = models.CharField("teléfono", max_length=9, validators=[validar_telefono])
    telefono_alterno = models.CharField(
        "teléfono alterno", max_length=9, blank=True, validators=[validar_telefono]
    )
    correo = models.EmailField("correo electrónico", blank=True)

    # --- Afiliación ---------------------------------------------------------
    afiliacion = models.CharField(
        "afiliación / seguro",
        max_length=10,
        choices=Afiliacion.choices,
        default=Afiliacion.NINGUNA,
    )
    numero_afiliacion = models.CharField("número de afiliación", max_length=30, blank=True)

    # --- Familia y responsable ----------------------------------------------
    nombre_madre = models.CharField("nombre de la madre", max_length=150, blank=True)
    nombre_padre = models.CharField("nombre del padre", max_length=150, blank=True)
    responsable_nombre = models.CharField(
        "nombre del responsable", max_length=150, blank=True
    )
    responsable_parentesco = models.CharField(
        "parentesco", max_length=10, choices=Parentesco.choices, blank=True
    )
    responsable_dui = models.CharField(
        "DUI del responsable", max_length=10, blank=True, validators=[validar_dui]
    )
    responsable_telefono = models.CharField(
        "teléfono del responsable", max_length=9, blank=True, validators=[validar_telefono]
    )

    # --- Datos del registro (Norma técnica del expediente, art. 15) ---------
    datos_proporcionados_por = models.CharField(
        "datos proporcionados por",
        max_length=150,
        blank=True,
        help_text="Déjelo vacío si los dio el mismo paciente. Si no, nombre y parentesco.",
    )
    observaciones = models.TextField(blank=True)
    consentimiento_datos = models.BooleanField(
        "consentimiento para el tratamiento de datos personales", default=False
    )
    fecha_consentimiento = models.DateTimeField(null=True, blank=True, editable=False)
    activo = models.BooleanField(default=True)
    texto_busqueda = models.CharField(max_length=500, blank=True, editable=False)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="registrado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="pacientes_registrados",
    )
    fecha_registro = models.DateTimeField("fecha y hora de registro", auto_now_add=True)
    fecha_actualizacion = models.DateTimeField("última actualización", auto_now=True)

    class Meta:
        ordering = ["primer_apellido", "segundo_apellido", "nombres"]
        indexes = [
            models.Index(fields=["primer_apellido", "nombres"], name="paciente_apellido_nombre"),
            models.Index(fields=["fecha_nacimiento"], name="paciente_fecha_nac"),
        ]

    def __str__(self):
        return self.nombre_completo

    def get_absolute_url(self):
        return reverse("pacientes:detalle", args=[self.pk])

    # --- Datos calculados ---------------------------------------------------
    @property
    def nombre_completo(self):
        partes = [self.nombres, self.primer_apellido, self.segundo_apellido]
        nombre = " ".join(parte for parte in partes if parte)
        if self.apellido_casada:
            nombre = f"{nombre} de {self.apellido_casada}"
        return nombre

    @property
    def edad(self):
        return calcular_edad(self.fecha_nacimiento) if self.fecha_nacimiento else None

    @property
    def edad_texto(self):
        return edad_en_texto(self.fecha_nacimiento) if self.fecha_nacimiento else ""

    @property
    def es_menor(self):
        edad = self.edad
        return edad is not None and edad < MAYORIA_DE_EDAD

    @property
    def numero_expediente(self):
        try:
            return self.historial.numero_expediente
        except HistorialClinico.DoesNotExist:
            return ""

    @staticmethod
    def calcular_clave_documento(tipo, numero):
        """Clave única del documento; DUI con o sin guion dan la misma clave."""
        if not numero or tipo == Paciente.TipoDocumento.NINGUNO:
            return None
        if tipo == Paciente.TipoDocumento.DUI:
            valor = solo_digitos(numero)
        else:
            valor = re.sub(r"[^0-9A-Z]", "", numero.upper())
        return f"{tipo}:{valor}" if valor else None

    # --- Validación ---------------------------------------------------------
    def clean(self):
        self._normalizar()
        errores = {}
        tipos = self.TipoDocumento
        edad = None

        if self.fecha_nacimiento:
            if self.fecha_nacimiento > timezone.localdate():
                errores["fecha_nacimiento"] = "La fecha de nacimiento no puede ser posterior a hoy."
            else:
                edad = calcular_edad(self.fecha_nacimiento)
                if edad > EDAD_MAXIMA:
                    errores["fecha_nacimiento"] = "Revise la fecha: la edad calculada pasa de 120 años."
                    edad = None

        # Número de documento según el tipo
        if self.tipo_documento == tipos.NINGUNO:
            if self.numero_documento:
                errores["numero_documento"] = "Deje este campo vacío si el paciente no presenta documento."
            if not self.observaciones.strip():
                errores["observaciones"] = "Anote por qué el paciente no presenta documento."
        elif not self.numero_documento:
            errores["numero_documento"] = "Escriba el número del documento."
        elif self.tipo_documento == tipos.DUI:
            try:
                validar_dui(self.numero_documento)
            except ValidationError as error:
                errores["numero_documento"] = error.messages[0]

        # Documento que corresponde según edad y nacionalidad
        salvadoreno = self.nacionalidad == self.Nacionalidad.SALVADORENA
        if "tipo_documento" not in errores and edad is not None:
            if edad < MAYORIA_DE_EDAD and self.tipo_documento == tipos.DUI:
                errores["tipo_documento"] = (
                    "El DUI se emite a partir de los 18 años. Para menores use NUI, CUN, "
                    "partida de nacimiento o carné de minoridad."
                )
            elif (
                edad >= MAYORIA_DE_EDAD
                and salvadoreno
                and self.tipo_documento not in (tipos.DUI, tipos.NINGUNO)
            ):
                errores["tipo_documento"] = "Para salvadoreños mayores de 18 años el documento es el DUI."
        if not salvadoreno and self.tipo_documento in (
            tipos.DUI,
            tipos.NUI,
            tipos.CUN,
            tipos.MINORIDAD,
        ):
            errores["tipo_documento"] = (
                "Para pacientes extranjeros use pasaporte, carné de residente o partida de nacimiento."
            )
        if not salvadoreno and not self.pais_origen:
            errores["pais_origen"] = "Indique el país de origen del paciente."

        # Los menores de edad deben tener un responsable
        if edad is not None and edad < MAYORIA_DE_EDAD:
            obligatorio = "Obligatorio para menores de 18 años."
            for campo in ("responsable_nombre", "responsable_parentesco", "responsable_telefono"):
                if not getattr(self, campo):
                    errores[campo] = obligatorio

        if errores:
            raise ValidationError(errores)

    def _normalizar(self):
        """Limpia espacios y deja documentos y teléfonos en formato estándar."""
        for campo in (
            "numero_documento",
            "nombres",
            "primer_apellido",
            "segundo_apellido",
            "apellido_casada",
            "conocido_por",
            "pais_origen",
            "ocupacion",
            "direccion",
            "punto_referencia",
            "numero_afiliacion",
            "nombre_madre",
            "nombre_padre",
            "responsable_nombre",
            "datos_proporcionados_por",
        ):
            setattr(self, campo, " ".join((getattr(self, campo) or "").split()))
        self.apellido_casada = re.sub(r"^de\s+", "", self.apellido_casada, flags=re.IGNORECASE)

        if self.tipo_documento == self.TipoDocumento.DUI:
            self.numero_documento = normalizar_dui(self.numero_documento)
        elif self.tipo_documento != self.TipoDocumento.NINGUNO:
            self.numero_documento = self.numero_documento.upper()
        if self.responsable_dui:
            self.responsable_dui = normalizar_dui(self.responsable_dui)
        for campo in ("telefono", "telefono_alterno", "responsable_telefono"):
            setattr(self, campo, normalizar_telefono(getattr(self, campo)))
        if self.nacionalidad == self.Nacionalidad.SALVADORENA:
            self.pais_origen = ""
        else:
            self.distrito_nacimiento = None

    # --- Guardado -----------------------------------------------------------
    def save(self, *args, **kwargs):
        self._normalizar()
        self.documento_clave = self.calcular_clave_documento(
            self.tipo_documento, self.numero_documento
        )
        self.texto_busqueda = normalizar_busqueda(
            " ".join(
                [
                    self.nombres,
                    self.primer_apellido,
                    self.segundo_apellido,
                    self.apellido_casada,
                    self.conocido_por,
                    self.numero_documento,
                    solo_digitos(self.numero_documento),
                ]
            )
        )[:500]
        if self.consentimiento_datos and not self.fecha_consentimiento:
            self.fecha_consentimiento = timezone.now()
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {
                "documento_clave",
                "texto_busqueda",
                "fecha_consentimiento",
            }

        creando = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if creando:
                # Composición 1 a 1: todo paciente nace con su expediente.
                self.obtener_historial()

    def obtener_historial(self):
        """Devuelve el expediente del paciente y lo crea si todavía no existe."""
        try:
            return self.historial
        except HistorialClinico.DoesNotExist:
            return HistorialClinico.objects.create(
                paciente=self,
                numero_expediente=HistorialClinico.generar_numero(self),
            )


# ---------------------------------------------------------------------------
# Historial clínico: el expediente (composición 1 a 1 con Paciente)
# ---------------------------------------------------------------------------


class HistorialClinico(models.Model):
    class TipoSangre(models.TextChoices):
        A_POS = "A+", "A+"
        A_NEG = "A-", "A-"
        B_POS = "B+", "B+"
        B_NEG = "B-", "B-"
        AB_POS = "AB+", "AB+"
        AB_NEG = "AB-", "AB-"
        O_POS = "O+", "O+"
        O_NEG = "O-", "O-"

    paciente = models.OneToOneField(
        Paciente, on_delete=models.CASCADE, related_name="historial"
    )
    numero_expediente = models.CharField(
        "número de expediente", max_length=20, unique=True, editable=False
    )
    fecha_apertura = models.DateTimeField("fecha de apertura", auto_now_add=True)
    tipo_sangre = models.CharField(
        "tipo de sangre", max_length=3, choices=TipoSangre.choices, blank=True
    )
    alergias = models.TextField(
        blank=True,
        help_text="Medicamentos, alimentos u otras sustancias. Vacío si no refiere.",
    )
    enfermedades_cronicas = models.TextField(
        "enfermedades crónicas", blank=True, help_text="Ej.: hipertensión, diabetes, asma."
    )
    medicamentos_actuales = models.TextField("medicamentos de uso continuo", blank=True)
    antecedentes_personales = models.TextField(
        "antecedentes personales",
        blank=True,
        help_text="Cirugías, hospitalizaciones, enfermedades importantes.",
    )
    antecedentes_familiares = models.TextField(
        "antecedentes familiares",
        blank=True,
        help_text="Enfermedades de padres, hermanos o abuelos.",
    )
    fecha_actualizacion = models.DateTimeField("última actualización", auto_now=True)

    class Meta:
        verbose_name = "historial clínico"
        verbose_name_plural = "historiales clínicos"

    def __str__(self):
        return f"Expediente {self.numero_expediente}"

    @staticmethod
    def generar_numero(paciente):
        """Número único por paciente: año de apertura + correlativo. Ej.: 2026-000125."""
        return f"{timezone.localdate().year}-{paciente.pk:06d}"
