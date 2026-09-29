from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import Movimiento, Producto


class ServiciosInventarioTests(TestCase):
    def setUp(self):
        self.hoy = timezone.localdate()
        self.producto = Producto.objects.create(codigo="MED-001", nombre="Acetaminofén", stock_minimo=10)

    def test_entrada_crea_lote_y_suma_stock(self):
        services.registrar_entrada(producto=self.producto, numero_lote="A1", cantidad=50)
        services.registrar_entrada(producto=self.producto, numero_lote="A1", cantidad=20)
        self.assertEqual(self.producto.stock_actual, 70)
        self.assertEqual(self.producto.lotes.count(), 1)
        self.assertEqual(Movimiento.objects.filter(tipo=Movimiento.Tipo.ENTRADA).count(), 2)

    def test_salida_usa_primero_el_lote_que_vence_antes(self):
        services.registrar_entrada(producto=self.producto, numero_lote="TARDE", cantidad=10,
                                   fecha_vencimiento=self.hoy + timedelta(days=300))
        services.registrar_entrada(producto=self.producto, numero_lote="PRONTO", cantidad=10,
                                   fecha_vencimiento=self.hoy + timedelta(days=20))
        movs = services.registrar_salida(producto=self.producto, cantidad=15)
        self.assertEqual([(m.lote.numero_lote, m.cantidad) for m in movs], [("PRONTO", 10), ("TARDE", 5)])
        self.assertEqual(self.producto.stock_actual, 5)

    def test_salida_no_toma_lotes_vencidos(self):
        services.registrar_entrada(producto=self.producto, numero_lote="VIEJO", cantidad=30,
                                   fecha_vencimiento=self.hoy - timedelta(days=1))
        with self.assertRaises(ValidationError):
            services.registrar_salida(producto=self.producto, cantidad=5)

    def test_salida_sin_stock_suficiente_no_cambia_nada(self):
        services.registrar_entrada(producto=self.producto, numero_lote="A1", cantidad=3)
        with self.assertRaises(ValidationError):
            services.registrar_salida(producto=self.producto, cantidad=5)
        self.assertEqual(self.producto.stock_actual, 3)
        self.assertFalse(Movimiento.objects.filter(tipo=Movimiento.Tipo.SALIDA).exists())


class VistasInventarioTests(TestCase):
    def test_flujo_basico(self):
        r = self.client.post(reverse("inventario:producto_crear"), {
            "codigo": "INS-01", "nombre": "Gasas", "tipo": "INS", "unidad_medida": "paquete",
            "stock_minimo": 10, "activo": "on",
        })
        p = Producto.objects.get(codigo="INS-01")
        self.assertRedirects(r, reverse("inventario:producto_detalle", args=[p.pk]))

        self.client.post(reverse("inventario:entrada", args=[p.pk]), {"numero_lote": "L1", "cantidad": 8})
        r = self.client.post(reverse("inventario:salida", args=[p.pk]), {"cantidad": 50})
        self.assertContains(r, "Stock insuficiente")

        for nombre in ["producto_lista", "movimiento_lista"]:
            self.assertEqual(self.client.get(reverse(f"inventario:{nombre}")).status_code, 200)
        self.assertContains(self.client.get(reverse("inventario:producto_lista") + "?filtro=bajo"), "Gasas", status_code=200)
