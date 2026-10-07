from django.urls import path

from . import views

app_name = "inventario"

urlpatterns = [
    path("", views.ProductoListView.as_view(), name="producto_lista"),
    path("productos/nuevo/", views.ProductoCreateView.as_view(), name="producto_crear"),
    path("productos/<int:pk>/", views.ProductoDetailView.as_view(), name="producto_detalle"),
    path("productos/<int:pk>/editar/", views.ProductoUpdateView.as_view(), name="producto_editar"),
    path("productos/<int:pk>/entrada/", views.registrar_entrada, name="entrada"),
    path("productos/<int:pk>/salida/", views.registrar_salida, name="salida"),
    path("movimientos/", views.MovimientoListView.as_view(), name="movimiento_lista"),
]
