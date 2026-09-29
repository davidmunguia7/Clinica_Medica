from django.contrib import admin

from .models import Lote, Movimiento, Producto


class LoteInline(admin.TabularInline):
    model = Lote
    extra = 0
    readonly_fields = ["cantidad_actual"]  # el stock se cambia solo con movimientos


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ["codigo", "nombre", "tipo", "stock_actual", "stock_minimo", "activo"]
    list_filter = ["tipo", "activo"]
    search_fields = ["codigo", "nombre"]
    inlines = [LoteInline]


@admin.register(Movimiento)
class MovimientoAdmin(admin.ModelAdmin):
    list_display = ["fecha", "tipo", "producto", "lote", "cantidad", "usuario", "motivo"]
    list_filter = ["tipo", "fecha"]
    search_fields = ["producto__nombre", "lote__numero_lote"]
    readonly_fields = [f.name for f in Movimiento._meta.fields]

    def has_add_permission(self, request):
        return False  # los movimientos se crean desde services.py
