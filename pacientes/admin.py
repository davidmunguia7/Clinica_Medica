from django.contrib import admin

from .models import Departamento, Distrito, HistorialClinico, Municipio, Paciente


@admin.register(Departamento)
class DepartamentoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo")
    search_fields = ("nombre",)


@admin.register(Municipio)
class MunicipioAdmin(admin.ModelAdmin):
    list_display = ("nombre", "departamento")
    list_filter = ("departamento",)
    search_fields = ("nombre",)


@admin.register(Distrito)
class DistritoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "municipio", "departamento")
    list_filter = ("municipio__departamento",)
    list_select_related = ("municipio__departamento",)
    search_fields = ("nombre", "municipio__nombre")

    @admin.display(description="departamento", ordering="municipio__departamento__nombre")
    def departamento(self, obj):
        return obj.municipio.departamento


class HistorialClinicoInline(admin.StackedInline):
    model = HistorialClinico
    can_delete = False
    extra = 0
    max_num = 1
    readonly_fields = ("numero_expediente", "fecha_apertura", "fecha_actualizacion")


@admin.register(Paciente)
class PacienteAdmin(admin.ModelAdmin):
    list_display = (
        "expediente",
        "nombre",
        "tipo_documento",
        "numero_documento",
        "edad",
        "telefono",
        "activo",
    )
    list_filter = ("activo", "sexo", "nacionalidad", "afiliacion", "distrito__municipio__departamento")
    list_select_related = ("historial",)
    search_fields = (
        "nombres",
        "primer_apellido",
        "segundo_apellido",
        "apellido_casada",
        "conocido_por",
        "numero_documento",
        "historial__numero_expediente",
    )
    readonly_fields = ("registrado_por", "fecha_registro", "fecha_actualizacion", "fecha_consentimiento")

    def get_inlines(self, request, obj):
        # Al crear, el expediente se genera solo; se edita desde la ficha ya guardada.
        return [HistorialClinicoInline] if obj else []

    def save_model(self, request, obj, form, change):
        if not change:
            obj.registrado_por = request.user
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        # Los expedientes clínicos se conservan (Norma técnica del expediente clínico).
        return request.user.is_superuser

    @admin.display(description="expediente", ordering="historial__numero_expediente")
    def expediente(self, obj):
        return obj.numero_expediente

    @admin.display(description="nombre", ordering="primer_apellido")
    def nombre(self, obj):
        return obj.nombre_completo

    @admin.display(description="edad")
    def edad(self, obj):
        return obj.edad_texto
