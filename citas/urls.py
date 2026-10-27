from django.urls import path

from . import views

app_name = "citas"

urlpatterns = [
    path("", views.agenda, name="agenda"),
    path("nueva/", views.nueva, name="nueva"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/estado/", views.cambiar_estado, name="cambiar_estado"),
    path("<int:pk>/recordar/", views.recordar, name="recordar"),
]
