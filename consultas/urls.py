from django.urls import path

from . import views

app_name = "consultas"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("atender/<int:cita_pk>/", views.atender, name="atender"),
    path("nueva/<int:paciente_pk>/", views.nueva, name="nueva"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/receta/", views.receta, name="receta"),
    path("por-entregar/", views.por_entregar, name="por_entregar"),
    path("<int:pk>/entregar/", views.entregar, name="entregar"),
]
