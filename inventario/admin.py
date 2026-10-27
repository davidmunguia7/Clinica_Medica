from django.contrib import admin
from django.db.models import Count

from .models import Categoria, Lote, Movimiento, Producto


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ["nombre", "descripcion", "orden", "num_productos"]
    list_editable = ["orden"]
    search_fields = ["nombre"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_productos=Count("productos"))

    @admin.display(description="productos", ordering="_productos")
    def num_productos(self, obj):
        return obj._productos


class LoteInline(admin.TabularInline):
    model = Lote
    extra = 0
    readonly_fields = ["cantidad_actual"]  # el stock se cambia solo con movimientos


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ["codigo", "nombre", "categoria", "tipo", "precio_venta", "stock_actual", "stock_minimo", "activo"]
    list_filter = ["categoria", "tipo", "activo"]
    list_select_related = ["categoria"]
    search_fields = ["codigo", "nombre"]
    inlines = [LoteInline]


@admin.register(Movimiento)
class MovimientoAdmin(admin.ModelAdmin):
    list_display = ["fecha", "tipo", "concepto", "producto", "lote", "cantidad", "precio_unitario", "usuario", "motivo"]
    list_filter = ["tipo", "concepto", "fecha"]
    list_select_related = ["producto", "lote", "usuario"]
    search_fields = ["producto__nombre", "lote__numero_lote"]
    readonly_fields = [f.name for f in Movimiento._meta.fields]

    def has_add_permission(self, request):
        return False  # los movimientos se crean desde services.py
