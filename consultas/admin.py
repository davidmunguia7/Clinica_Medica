from django.contrib import admin

from .models import Consulta, MedicamentoRecetado


class MedicamentoRecetadoInline(admin.TabularInline):
    model = MedicamentoRecetado
    extra = 0
    fields = ("producto", "nombre", "dosis", "frecuencia", "duracion", "cantidad", "estado", "entregado_en", "entregado_por")
    readonly_fields = ("estado", "entregado_en", "entregado_por")
    raw_id_fields = ("producto",)


@admin.register(Consulta)
class ConsultaAdmin(admin.ModelAdmin):
    list_display = ("fecha", "paciente", "medico", "cita")
    list_filter = ("medico", "fecha")
    list_select_related = ("paciente__historial", "medico", "cita")
    date_hierarchy = "fecha"
    search_fields = ("paciente__nombres", "paciente__primer_apellido", "paciente__historial__numero_expediente")
    raw_id_fields = ("paciente", "cita")
    inlines = [MedicamentoRecetadoInline]

    def has_delete_permission(self, request, obj=None):
        # Las consultas son parte del expediente clínico: se conservan
        return request.user.is_superuser
