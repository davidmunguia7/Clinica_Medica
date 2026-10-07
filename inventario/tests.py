from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
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
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser("admin", "admin@example.com", "clave-de-prueba-123")
        self.client.force_login(self.admin)

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

    def test_movimiento_guarda_el_usuario(self):
        p = Producto.objects.create(codigo="MED-002", nombre="Ibuprofeno", stock_minimo=5)
        self.client.post(reverse("inventario:entrada", args=[p.pk]), {"numero_lote": "L1", "cantidad": 8})
        self.assertEqual(Movimiento.objects.get(producto=p).usuario, self.admin)

    def test_aviso_de_productos_bajo_el_minimo(self):
        url = reverse("inventario:producto_lista")
        self.assertNotContains(self.client.get(url), "por debajo de su existencia mínima")
        Producto.objects.create(codigo="MED-003", nombre="Amoxicilina", stock_minimo=10)
        self.assertContains(self.client.get(url), "1 producto en o por debajo de su existencia mínima")

    def test_requiere_iniciar_sesion(self):
        self.client.logout()
        p = Producto.objects.create(codigo="MED-004", nombre="Loratadina")
        for url in [
            reverse("inventario:producto_lista"),
            reverse("inventario:producto_detalle", args=[p.pk]),
            reverse("inventario:producto_crear"),
            reverse("inventario:entrada", args=[p.pk]),
            reverse("inventario:movimiento_lista"),
        ]:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertIn(reverse("login"), r["Location"])

    def test_usuario_sin_permiso(self):
        usuario = get_user_model().objects.create_user("visitante", password="clave-de-prueba-123")
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(reverse("inventario:producto_lista")).status_code, 403)

        usuario.user_permissions.add(Permission.objects.get(codename="view_producto"))
        self.client.force_login(get_user_model().objects.get(pk=usuario.pk))
        self.assertEqual(self.client.get(reverse("inventario:producto_lista")).status_code, 200)
        self.assertEqual(self.client.get(reverse("inventario:producto_crear")).status_code, 403)
