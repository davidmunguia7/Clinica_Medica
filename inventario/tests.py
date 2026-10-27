from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import Categoria, Lote, Movimiento, Producto
from .templatetags.inventario_extras import dinero


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


class PreciosYConceptosTests(TestCase):
    def setUp(self):
        self.producto = Producto.objects.create(
            codigo="MED-002", nombre="Loratadina 10 mg", precio_venta=Decimal("0.50")
        )

    def test_compra_guarda_el_costo_en_el_lote_y_en_el_movimiento(self):
        mov = services.registrar_entrada(
            producto=self.producto, numero_lote="L1", cantidad=100, costo_unitario=Decimal("0.20")
        )
        self.assertEqual(mov.concepto, Movimiento.Concepto.COMPRA)
        self.assertEqual(mov.total, Decimal("20.00"))
        self.assertEqual(Lote.objects.get(numero_lote="L1").costo_unitario, Decimal("0.20"))
        # Otra compra del mismo lote a otro precio: el lote se queda con el último costo
        services.registrar_entrada(
            producto=self.producto, numero_lote="L1", cantidad=10, costo_unitario=Decimal("0.25")
        )
        self.assertEqual(Lote.objects.get(numero_lote="L1").costo_unitario, Decimal("0.25"))

    def test_venta_usa_el_precio_del_producto_si_no_se_indica(self):
        services.registrar_entrada(producto=self.producto, numero_lote="L1", cantidad=10)
        (venta,) = services.registrar_salida(producto=self.producto, cantidad=4)
        self.assertEqual(venta.concepto, Movimiento.Concepto.VENTA)
        self.assertEqual(venta.precio_unitario, Decimal("0.50"))
        self.assertEqual(venta.total, Decimal("2.00"))
        (rebajada,) = services.registrar_salida(
            producto=self.producto, cantidad=1, precio_unitario=Decimal("0.40")
        )
        self.assertEqual(rebajada.precio_unitario, Decimal("0.40"))

    def test_producto_sin_precio_deja_la_venta_sin_precio(self):
        sin_precio = Producto.objects.create(codigo="MED-003", nombre="Jarabe")
        services.registrar_entrada(producto=sin_precio, numero_lote="J1", cantidad=5)
        (venta,) = services.registrar_salida(producto=sin_precio, cantidad=1)
        self.assertIsNone(venta.precio_unitario)
        self.assertIsNone(venta.total)

    def test_uso_en_consulta_guarda_el_costo_de_cada_lote(self):
        hoy = timezone.localdate()
        services.registrar_entrada(producto=self.producto, numero_lote="A", cantidad=2, costo_unitario=Decimal("0.10"),
                                   fecha_vencimiento=hoy + timedelta(days=10))
        services.registrar_entrada(producto=self.producto, numero_lote="B", cantidad=5, costo_unitario=Decimal("0.30"),
                                   fecha_vencimiento=hoy + timedelta(days=90))
        movs = services.registrar_salida(producto=self.producto, cantidad=3, concepto=Movimiento.Concepto.USO_INTERNO)
        self.assertEqual([(m.lote.numero_lote, m.precio_unitario) for m in movs],
                         [("A", Decimal("0.10")), ("B", Decimal("0.30"))])

    def test_concepto_que_no_corresponde(self):
        with self.assertRaises(ValidationError):
            services.registrar_entrada(producto=self.producto, numero_lote="L1", cantidad=1,
                                       concepto=Movimiento.Concepto.VENTA)
        services.registrar_entrada(producto=self.producto, numero_lote="L1", cantidad=1)
        with self.assertRaises(ValidationError):
            services.registrar_salida(producto=self.producto, cantidad=1, concepto=Movimiento.Concepto.COMPRA)

    def test_formato_de_dinero(self):
        self.assertEqual(dinero(Decimal("1234.5")), "$1,234.50")
        self.assertEqual(dinero(None), "—")
        self.assertEqual(dinero(Decimal("-2")), "−$2.00")


class VentasDesdeLaPantallaTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser("caja", "caja@example.com", "clave-de-prueba-123")
        self.client.force_login(self.admin)

    def test_venta_sin_precio_avisa(self):
        p = Producto.objects.create(codigo="MED-9", nombre="Suero oral")
        services.registrar_entrada(producto=p, numero_lote="S1", cantidad=5)
        r = self.client.post(reverse("inventario:salida", args=[p.pk]), {"cantidad": 1, "concepto": "VENTA"}, follow=True)
        self.assertContains(r, "La venta quedó sin precio")

    def test_salida_que_no_es_venta_no_guarda_el_precio_escrito(self):
        p = Producto.objects.create(codigo="MED-8", nombre="Ibuprofeno", precio_venta=Decimal("0.35"))
        services.registrar_entrada(producto=p, numero_lote="I1", cantidad=5, costo_unitario=Decimal("0.12"))
        self.client.post(reverse("inventario:salida", args=[p.pk]),
                         {"cantidad": 2, "concepto": "USO", "precio_unitario": "9.99"})
        mov = Movimiento.objects.get(tipo=Movimiento.Tipo.SALIDA)
        self.assertEqual(mov.precio_unitario, Decimal("0.12"))  # costo del lote, no lo escrito

    def test_producto_con_categoria_y_precio(self):
        gripe = Categoria.objects.get(nombre="Gripe y resfriado")
        self.client.post(reverse("inventario:producto_crear"), {
            "codigo": "MED-20", "nombre": "Antigripal", "tipo": "MED", "categoria": gripe.pk,
            "unidad_medida": "tableta", "stock_minimo": 10, "precio_venta": "0.25", "activo": "on",
        })
        producto = Producto.objects.get(codigo="MED-20")
        self.assertEqual((producto.categoria, producto.precio_venta), (gripe, Decimal("0.25")))
        # Una compra con su costo y una venta sin escribir el precio
        self.client.post(reverse("inventario:entrada", args=[producto.pk]),
                         {"numero_lote": "G1", "cantidad": 20, "concepto": "COMPRA", "costo_unitario": "0.10"})
        self.client.post(reverse("inventario:salida", args=[producto.pk]), {"cantidad": 4, "concepto": "VENTA"})
        compra = Movimiento.objects.get(tipo=Movimiento.Tipo.ENTRADA)
        venta = Movimiento.objects.get(tipo=Movimiento.Tipo.SALIDA)
        self.assertEqual((compra.concepto, compra.total), (Movimiento.Concepto.COMPRA, Decimal("2.00")))
        self.assertEqual((venta.concepto, venta.total), (Movimiento.Concepto.VENTA, Decimal("1.00")))


class CategoriasYPanelTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser("bodega", "bodega@example.com", "clave-de-prueba-123")
        self.client.force_login(self.admin)
        self.respiratorias = Categoria.objects.get(nombre="Vías respiratorias")
        self.gripe = Categoria.objects.get(nombre="Gripe y resfriado")
        self.salbutamol = Producto.objects.create(
            codigo="MED-10", nombre="Salbutamol inhalador", categoria=self.respiratorias,
            stock_minimo=5, precio_venta=Decimal("6.00"),
        )
        self.antigripal = Producto.objects.create(
            codigo="MED-11", nombre="Antigripal tabletas", categoria=self.gripe,
            stock_minimo=50, precio_venta=Decimal("0.25"),
        )
        self.sin_categoria = Producto.objects.create(codigo="OTR-1", nombre="Termómetro", stock_minimo=0)
        services.registrar_entrada(producto=self.salbutamol, numero_lote="S1", cantidad=20,
                                   costo_unitario=Decimal("3.50"))
        services.registrar_entrada(producto=self.antigripal, numero_lote="G1", cantidad=40,
                                   costo_unitario=Decimal("0.10"))
        services.registrar_salida(producto=self.salbutamol, cantidad=2)  # venta a $6.00

    def test_categorias_iniciales(self):
        nombres = set(Categoria.objects.values_list("nombre", flat=True))
        self.assertTrue({"Vías respiratorias", "Gripe y resfriado", "Antibióticos", "Otros"} <= nombres)

    def test_filtrar_la_lista_por_categoria(self):
        url = reverse("inventario:producto_lista")
        r = self.client.get(url, {"categoria": self.respiratorias.pk})
        self.assertContains(r, "Salbutamol")
        self.assertNotContains(r, "Antigripal")
        r = self.client.get(url, {"categoria": "sin"})
        self.assertContains(r, "Termómetro")
        self.assertNotContains(r, "Salbutamol")

    def test_numeros_del_panel(self):
        r = self.client.get(reverse("inventario:panel"))
        self.assertEqual(r.status_code, 200)
        filas = {(f["categoria"].nombre if f["categoria"] else None): f for f in r.context["categorias"]}

        respiratorias = filas["Vías respiratorias"]
        self.assertEqual(respiratorias["productos"], 1)
        self.assertEqual(respiratorias["unidades"], 18)
        self.assertEqual(respiratorias["valor"], Decimal("63.00"))  # 18 × $3.50
        self.assertEqual(respiratorias["vendido_unidades"], 2)
        self.assertEqual(respiratorias["vendido_monto"], Decimal("12.00"))
        self.assertEqual(respiratorias["bajo_minimo"], 0)

        gripe = filas["Gripe y resfriado"]
        self.assertEqual(gripe["bajo_minimo"], 1)  # 40 de existencia y mínimo 50
        self.assertEqual(gripe["valor"], Decimal("4.00"))

        self.assertIn(None, filas)  # aparece «Sin categoría» porque hay un producto sin asignar
        self.assertEqual(r.context["total_valor"], Decimal("67.00"))
        self.assertEqual(r.context["mes"]["ventas"]["monto"], Decimal("12.00"))
        self.assertEqual(r.context["mes"]["compras"]["monto"], Decimal("74.00"))  # 70 + 4
        # El termómetro (0 de existencia, mínimo 0) también se cuenta por reabastecer
        self.assertEqual(r.context["total_reabastecer"], 2)
        self.assertContains(r, "$67.00")
        self.assertContains(r, "Antigripal tabletas")

    def test_panel_requiere_permiso(self):
        usuario = get_user_model().objects.create_user("recepcion", password="clave-de-prueba-123")
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(reverse("inventario:panel")).status_code, 403)
        usuario.user_permissions.add(Permission.objects.get(codename="view_producto"))
        self.assertEqual(self.client.get(reverse("inventario:panel")).status_code, 200)

    def test_agregar_producto_desde_una_categoria(self):
        r = self.client.get(reverse("inventario:producto_crear"), {"categoria": self.gripe.pk})
        self.assertEqual(r.context["form"].initial["categoria"], str(self.gripe.pk))

    def test_panel_requiere_iniciar_sesion(self):
        self.client.logout()
        respuesta = self.client.get(reverse("inventario:panel"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("login"), respuesta["Location"])
