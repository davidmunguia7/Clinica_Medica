from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from citas.models import Cita, MensajeSMS
from inventario import services
from inventario.models import Categoria, Movimiento, Producto
from pacientes.models import Paciente
from pacientes.tests import DUI_1, crear_paciente

from . import calculos

User = get_user_model()


def fecha(mes, dia, hora=10):
    return timezone.make_aware(datetime(2026, mes, dia, hora, 0))


class ReporteMensualTests(TestCase):
    """Marzo de 2026 con datos conocidos; febrero sirve para la comparación."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("direccion", "direccion@example.com", "clave-de-prueba-123")
        cls.medica = User.objects.create_user(
            "dra.lopez", password="clave-de-prueba-123", first_name="Ana", last_name="López", rol="MEDICO"
        )
        juan = crear_paciente()
        rosa = crear_paciente(nombres="Rosa", primer_apellido="Martínez", numero_documento=DUI_1)
        Paciente.objects.filter(pk=juan.pk).update(fecha_registro=fecha(3, 2))
        Paciente.objects.filter(pk=rosa.pk).update(fecha_registro=fecha(2, 10))

        def cita(paciente, cuando, estado, medico=cls.medica):
            return Cita.objects.create(paciente=paciente, medico=medico, fecha_hora=cuando,
                                       motivo="Control", estado=estado)

        atendida = cita(juan, fecha(3, 10), Cita.Estado.ATENDIDA)
        cita(juan, fecha(3, 20), Cita.Estado.ATENDIDA)
        cita(rosa, fecha(3, 21), Cita.Estado.CANCELADA)
        cita(rosa, fecha(3, 22), Cita.Estado.NO_ASISTIO, medico=None)
        cita(rosa, fecha(2, 15), Cita.Estado.ATENDIDA)  # febrero
        mensaje = MensajeSMS.objects.create(cita=atendida, telefono="7123-4567", texto="Recordatorio",
                                            estado=MensajeSMS.Estado.SIMULADO, proveedor="simulado")
        MensajeSMS.objects.filter(pk=mensaje.pk).update(creado=fecha(3, 9))

        cls.salbutamol = Producto.objects.create(
            codigo="MED-1", nombre="Salbutamol inhalador", precio_venta=Decimal("6.00"),
            categoria=Categoria.objects.get(nombre="Vías respiratorias"),
        )
        services.registrar_entrada(producto=cls.salbutamol, numero_lote="S1", cantidad=10,
                                   costo_unitario=Decimal("3.50"))
        services.registrar_salida(producto=cls.salbutamol, cantidad=4)  # venta: 4 × $6.00
        services.registrar_salida(producto=cls.salbutamol, cantidad=1,
                                  concepto=Movimiento.Concepto.USO_INTERNO)  # a costo: $3.50
        Movimiento.objects.update(fecha=fecha(3, 5))
        compra_febrero = services.registrar_entrada(producto=cls.salbutamol, numero_lote="S0", cantidad=5,
                                                    costo_unitario=Decimal("4.00"))
        Movimiento.objects.filter(pk=compra_febrero.pk).update(fecha=fecha(2, 3))

    def test_numeros_del_mes(self):
        r = calculos.reporte_mensual(2026, 3)
        self.assertEqual(r["titulo"], "Marzo de 2026")
        self.assertEqual((r["desde"], r["hasta"]), (date(2026, 3, 1), date(2026, 3, 31)))
        self.assertEqual(r["pacientes"]["nuevos"], 1)

        citas = r["citas"]
        self.assertEqual((citas["total"], citas["atendidas"], citas["canceladas"], citas["no_asistio"]), (4, 2, 1, 1))
        self.assertEqual(citas["pacientes_atendidos"], 1)  # Juan vino dos veces
        self.assertEqual(citas["por_medico"][0], {"nombre": "Ana López", "total": 3, "atendidas": 2})
        self.assertEqual(citas["por_medico"][1]["nombre"], "Sin médico asignado")
        self.assertEqual(citas["recordatorios"]["simulados"], 1)

        inv = r["inventario"]
        self.assertEqual((inv["compras"]["unidades"], inv["compras"]["monto"]), (10, Decimal("35.00")))
        self.assertEqual((inv["ventas"]["unidades"], inv["ventas"]["monto"]), (4, Decimal("24.00")))
        self.assertEqual((inv["uso"]["unidades"], inv["uso"]["monto"]), (1, Decimal("3.50")))
        self.assertEqual(inv["margen"]["costo"], Decimal("14.00"))
        self.assertEqual(inv["margen"]["margen"], Decimal("10.00"))
        self.assertEqual(inv["margen"]["porcentaje"], 42)
        self.assertEqual(inv["ventas_por_categoria"], [
            {"categoria": "Vías respiratorias", "unidades": 4, "monto": Decimal("24.00"), "porcentaje": 100}
        ])
        self.assertEqual(inv["mas_vendidos"][0]["producto"], "Salbutamol inhalador")

    def test_comparacion_con_el_mes_anterior(self):
        comparacion = {f["nombre"]: f for f in calculos.reporte_mensual(2026, 3)["comparacion"]}
        self.assertEqual(comparacion["Citas atendidas"]["anterior"], 1)
        self.assertEqual(comparacion["Citas atendidas"]["variacion"], 100)
        self.assertEqual(comparacion["Compras"]["anterior"], Decimal("20.00"))
        self.assertEqual(comparacion["Compras"]["variacion"], 75)  # de $20 a $35
        self.assertIsNone(comparacion["Ventas"]["variacion"])  # en febrero no hubo ventas
        self.assertEqual(comparacion["Pacientes nuevos"]["variacion"], 0)

    def test_pantalla_del_reporte(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("reportes:mensual"), {"mes": "2026-03"})
        self.assertEqual(r.status_code, 200)
        for texto in ("Marzo de 2026", "$24.00", "$10.00", "Salbutamol inhalador", "Ana López", "Vías respiratorias"):
            self.assertContains(r, texto)

    def test_descargar_csv(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("reportes:mensual"), {"mes": "2026-03", "formato": "csv"})
        self.assertEqual(r["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("reporte-2026-03.csv", r["Content-Disposition"])
        contenido = r.content.decode("utf-8")
        self.assertTrue(contenido.startswith("﻿"))
        self.assertIn("Ventas,4,24.00,0", contenido)
        self.assertIn("Vías respiratorias,4,24.00", contenido)

    def test_cada_quien_ve_solo_lo_que_le_corresponde(self):
        medico = User.objects.create_user("medico", password="clave-de-prueba-123")
        medico.user_permissions.add(Permission.objects.get(codename="view_cita"))
        self.client.force_login(medico)
        r = self.client.get(reverse("reportes:mensual"), {"mes": "2026-03"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("citas", r.context["r"])
        self.assertNotIn("inventario", r.context["r"])
        self.assertNotContains(r, "$24.00")
        self.assertContains(r, "no tiene permiso para ver el dinero")

        sin_permisos = User.objects.create_user("visitante", password="clave-de-prueba-123")
        self.client.force_login(sin_permisos)
        self.assertEqual(self.client.get(reverse("reportes:mensual")).status_code, 403)

        self.client.logout()
        respuesta = self.client.get(reverse("reportes:mensual"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("login"), respuesta["Location"])

    def test_mes_mal_escrito_muestra_el_actual(self):
        hoy = date(2026, 10, 7)
        self.assertEqual(calculos.leer_mes("2026-03", hoy), (2026, 3))
        for texto in ("", None, "2026-13", "marzo", "1999-01"):
            self.assertEqual(calculos.leer_mes(texto, hoy), (2026, 10), texto)
        self.assertEqual(calculos.mes_anterior(2026, 1), (2025, 12))
        self.assertEqual(calculos.mes_siguiente(2026, 12), (2027, 1))

    def test_reportes_lleva_al_reporte_mensual(self):
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.get("/reportes/"), reverse("reportes:mensual"))
