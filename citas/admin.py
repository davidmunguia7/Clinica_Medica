from django.contrib import admin

from .models import Cita, MensajeSMS


class MensajeSMSInline(admin.TabularInline):
    model = MensajeSMS
    extra = 0
    can_delete = False
    fields = ("creado", "estado", "proveedor", "telefono", "texto", "error")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Cita)
class CitaAdmin(admin.ModelAdmin):
    list_display = ("fecha_hora", "paciente", "medico", "estado", "recordatorio_enviado")
    list_filter = ("estado", "medico")
    date_hierarchy = "fecha_hora"
    search_fields = ("paciente__nombres", "paciente__primer_apellido", "paciente__historial__numero_expediente")
    autocomplete_fields = ()
    raw_id_fields = ("paciente",)
    inlines = [MensajeSMSInline]


@admin.register(MensajeSMS)
class MensajeSMSAdmin(admin.ModelAdmin):
    list_display = ("creado", "cita", "estado", "proveedor")
    list_filter = ("estado", "proveedor")
    readonly_fields = ("cita", "telefono", "texto", "estado", "proveedor", "id_externo", "error", "enviado_por", "creado")

    def has_add_permission(self, request):
        return False
