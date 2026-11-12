from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from citas.models import Cita
from inventario import services
from inventario.models import Movimiento, Producto
from pacientes.tests import DUI_1, crear_paciente
from sistema_clinico.cifrado import PREFIJO_FERNET

from . import alergias, entregas
from .forms import FILAS_EN_BLANCO
from .models import Consulta, MedicamentoRecetado

User = get_user_model()
CLAVE = "clave-de-prueba-123"
Estado = MedicamentoRecetado.Estado


def hoy_a_las(hora):
    return timezone.make_aware(datetime.combine(timezone.localdate(), time(hora, 0)))


def datos_consulta(medicamentos=(), **campos):
    """Datos del formulario de consulta con su receta (como los manda el navegador)."""
    datos = {
        "motivo": "Fiebre y dolor de garganta",
        "sintomas": "Fiebre de 38.5 °C desde ayer",
        "diagnostico": "Faringitis aguda",
        "indicaciones": "Reposo y abundantes líquidos",
        "medicamentos-TOTAL_FORMS": "4",
        "medicamentos-INITIAL_FORMS": "0",
        "medicamentos-MIN_NUM_FORMS": "0",
        "medicamentos-MAX_NUM_FORMS": "1000",
    }
    for i in range(4):
        datos.update({f"medicamentos-{i}-{campo}": "" for campo in
                      ("producto", "nombre", "dosis", "frecuencia", "duracion", "indicaciones")})
        datos[f"medicamentos-{i}-cantidad"] = "1"
    for i, medicamento in enumerate(medicamentos):
        datos.update({f"medicamentos-{i}-{campo}": str(valor) for campo, valor in medicamento.items()})
    datos.update(campos)
    return datos


class ConsultasYRecetasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.medica = User.objects.create_user("dra.lopez", password=CLAVE, rol="MEDICO",
                                              first_name="Ana", last_name="López")
        cls.medico_2 = User.objects.create_user("dr.ramos", password=CLAVE, rol="MEDICO")
        cls.recepcion = User.objects.create_user("secretaria", password=CLAVE, rol="RECEPCION")
        cls.admin = User.objects.create_user("direccion", password=CLAVE, rol="ADMIN")
        cls.paciente = crear_paciente()
        historial = cls.paciente.historial
        historial.alergias = "Alergia a la penicilina"
        historial.save()

        cls.acetaminofen = Producto.objects.create(
            codigo="MED-001", nombre="Acetaminofén", presentacion="tableta 500 mg",
            unidad_medida="tableta", stock_minimo=5, precio_venta="0.25",
        )
        hoy = timezone.localdate()
        services.registrar_entrada(producto=cls.acetaminofen, numero_lote="PRONTO", cantidad=6,
                                   fecha_vencimiento=hoy + timedelta(days=20), costo_unitario="0.10")
        services.registrar_entrada(producto=cls.acetaminofen, numero_lote="TARDE", cantidad=20,
                                   fecha_vencimiento=hoy + timedelta(days=300), costo_unitario="0.12")
        services.registrar_entrada(producto=cls.acetaminofen, numero_lote="VENCIDO", cantidad=50,
                                   fecha_vencimiento=hoy - timedelta(days=1))

    def setUp(self):
        self.cita = Cita.objects.create(paciente=self.paciente, medico=self.medica,
                                        fecha_hora=hoy_a_las(9), motivo="Fiebre")

    def entrar(self, usuario):
        self.client.force_login(usuario)

    def atender(self, medicamentos=(), **campos):
        return self.client.post(reverse("consultas:atender", args=[self.cita.pk]),
                                datos_consulta(medicamentos, **campos))

    def receta_con_acetaminofen(self, cantidad=10):
        self.entrar(self.medica)
        self.atender([
            {"producto": self.acetaminofen.pk, "dosis": "1 tableta", "frecuencia": "cada 8 horas",
             "duracion": "por 3 días", "cantidad": cantidad},
            {"nombre": "Ibuprofeno jarabe", "dosis": "5 ml", "frecuencia": "cada 12 horas", "cantidad": 1},
        ])
        return Consulta.objects.get()

    # ---- Atender y recetar ----

    def test_el_medico_atiende_la_cita_y_receta(self):
        self.entrar(self.medica)
        formulario = self.client.get(reverse("consultas:atender", args=[self.cita.pk]))
        self.assertContains(formulario, "Alergia a la penicilina")  # las alergias a la vista
        # Lo que se puede entregar: 6 + 20 (el lote vencido de 50 no cuenta)
        self.assertContains(formulario, "Acetaminofén · tableta 500 mg (hay 26 tableta)")
        self.assertEqual(formulario.context["form"]["motivo"].value(), "Fiebre")  # viene de la cita

        consulta = self.receta_con_acetaminofen()
        self.assertEqual((consulta.paciente, consulta.medico, consulta.cita), (self.paciente, self.medica, self.cita))
        self.assertEqual(consulta.diagnostico, "Faringitis aguda")
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, Cita.Estado.ATENDIDA)

        de_farmacia, de_afuera = consulta.medicamentos.all()
        self.assertEqual((de_farmacia.estado, de_farmacia.cantidad), (Estado.POR_ENTREGAR, 10))
        self.assertEqual(de_afuera.estado, Estado.AFUERA)  # la clínica no lo tiene
        self.assertEqual(de_afuera.nombre_medicamento, "Ibuprofeno jarabe")
        # Recetar NO descuenta: se descuenta al entregar
        self.assertEqual(services.disponible(self.acetaminofen), 26)
        self.assertFalse(Movimiento.objects.filter(tipo=Movimiento.Tipo.SALIDA).exists())

    def test_receta_sencilla_y_sin_perder_lo_escrito(self):
        self.entrar(self.medica)
        formulario = self.client.get(reverse("consultas:atender", args=[self.cita.pk]))
        # Filas para varios medicamentos, pero en la pantalla se ve una y las demás con el botón
        self.assertEqual(len(formulario.context["formset"].forms), FILAS_EN_BLANCO)
        self.assertContains(formulario, "+ Agregar otro medicamento")
        self.assertNotContains(formulario, "data-medicamento data-con-datos")  # (el script también nombra el atributo)
        # Si la sesión se cierra a medio escribir, lo escrito se recupera al volver a entrar
        self.assertContains(formulario, "data-borrador")
        self.assertContains(formulario, "borrador:")
        # Una fila con error queda a la vista para corregirla
        respuesta = self.atender([{"dosis": "1 tableta", "frecuencia": "cada 8 horas"}])
        self.assertContains(respuesta, "data-medicamento data-con-datos", count=1)

    def test_volver_a_atender_abre_la_consulta_que_ya_existe(self):
        consulta = self.receta_con_acetaminofen()
        respuesta = self.client.get(reverse("consultas:atender", args=[self.cita.pk]))
        self.assertRedirects(respuesta, consulta.get_absolute_url())

    def test_no_se_atiende_una_cita_cancelada(self):
        self.cita.estado = Cita.Estado.CANCELADA
        self.cita.save()
        self.entrar(self.medica)
        self.assertRedirects(self.client.get(reverse("consultas:atender", args=[self.cita.pk])),
                             self.cita.get_absolute_url())

    def test_consulta_sin_cita(self):
        self.entrar(self.medica)
        respuesta = self.client.post(reverse("consultas:nueva", args=[self.paciente.pk]), datos_consulta())
        consulta = Consulta.objects.get()
        self.assertRedirects(respuesta, consulta.get_absolute_url())
        self.assertIsNone(consulta.cita)

    def test_medicamento_sin_nombre_no_se_guarda(self):
        self.entrar(self.medica)
        respuesta = self.atender([{"dosis": "1 tableta", "frecuencia": "cada 8 horas"}])
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Elija un medicamento de la farmacia o escriba su nombre.")
        self.assertFalse(Consulta.objects.exists())

    def test_diagnostico_obligatorio(self):
        self.entrar(self.medica)
        self.assertEqual(self.atender(diagnostico="").status_code, 200)
        self.assertFalse(Consulta.objects.exists())

    # ---- Alergias ----

    def test_aviso_de_alergia_antes_de_guardar(self):
        self.entrar(self.medica)
        penicilina = [{"nombre": "Penicilina benzatínica", "dosis": "1 ampolla", "frecuencia": "dosis única"}]
        respuesta = self.atender(penicilina)
        self.assertContains(respuesta, "Revise las alergias antes de guardar")
        self.assertFalse(Consulta.objects.exists())
        # Si el médico confirma que lo revisó, se guarda
        self.atender(penicilina, confirmo_alergias="1")
        self.assertEqual(Consulta.objects.get().medicamentos.get().nombre, "Penicilina benzatínica")

    def test_coincidencias_de_alergias(self):
        self.assertEqual(alergias.coincidencias("Alergia a la penicilina", ["PENICILINA G", "Acetaminofén"]),
                         [("PENICILINA G", ["penicilina"])])
        self.assertEqual(alergias.coincidencias("Ibuprofeno, sulfas", ["Ibuprofeno 400 mg"]),
                         [("Ibuprofeno 400 mg", ["ibuprofeno"])])
        self.assertEqual(alergias.coincidencias("Niega alergias", ["Penicilina"]), [])
        self.assertEqual(alergias.coincidencias("", ["Penicilina"]), [])

    # ---- Entregar (aquí se descuenta del inventario) ----

    def test_recepcion_entrega_y_se_descuenta_del_inventario(self):
        consulta = self.receta_con_acetaminofen(cantidad=10)
        medicamento = consulta.medicamentos.get(estado=Estado.POR_ENTREGAR)
        self.entrar(self.recepcion)
        lista = self.client.get(reverse("consultas:por_entregar"))
        self.assertContains(lista, self.paciente.nombre_completo)
        self.assertContains(self.client.get(reverse("inicio")), "Recetas por entregar")

        pantalla = self.client.get(reverse("consultas:entregar", args=[consulta.pk]))
        self.assertNotContains(pantalla, "Faringitis")  # Recepción no ve el diagnóstico
        respuesta = self.client.post(reverse("consultas:entregar", args=[consulta.pk]), {
            f"accion-{medicamento.pk}": "entregar", "concepto": Movimiento.Concepto.VENTA,
        })
        self.assertRedirects(respuesta, reverse("consultas:por_entregar"))

        medicamento.refresh_from_db()
        self.assertEqual((medicamento.estado, medicamento.entregado_por), (Estado.ENTREGADO, self.recepcion))
        self.assertIsNotNone(medicamento.entregado_en)
        # Primero el lote que vence antes (6) y luego el siguiente (4); el vencido no se toca
        salidas = list(medicamento.movimientos.order_by("pk"))
        self.assertEqual([(m.lote.numero_lote, m.cantidad) for m in salidas], [("PRONTO", 6), ("TARDE", 4)])
        for salida in salidas:
            self.assertEqual((salida.paciente, salida.usuario, salida.concepto),
                             (self.paciente, self.recepcion, Movimiento.Concepto.VENTA))
            self.assertEqual(str(salida.precio_unitario), "0.25")
        self.assertEqual(services.disponible(self.acetaminofen), 16)
        self.assertNotContains(self.client.get(reverse("consultas:por_entregar")), self.paciente.nombre_completo)

    def test_entrega_sin_costo_queda_como_uso_en_consulta(self):
        consulta = self.receta_con_acetaminofen(cantidad=2)
        medicamento = consulta.medicamentos.get(estado=Estado.POR_ENTREGAR)
        entregas.entregar(medicamento, usuario=self.recepcion, concepto=Movimiento.Concepto.USO_INTERNO)
        salida = Movimiento.objects.get(tipo=Movimiento.Tipo.SALIDA)
        self.assertEqual((salida.concepto, str(salida.precio_unitario)), (Movimiento.Concepto.USO_INTERNO, "0.10"))

    def test_si_no_alcanza_no_se_entrega_ni_se_descuenta(self):
        consulta = self.receta_con_acetaminofen(cantidad=40)  # hay 26 utilizables
        medicamento = consulta.medicamentos.get(estado=Estado.POR_ENTREGAR)
        self.entrar(self.recepcion)
        pantalla = self.client.get(reverse("consultas:entregar", args=[consulta.pk]))
        self.assertContains(pantalla, "No alcanza lo que hay en la farmacia")
        respuesta = self.client.post(reverse("consultas:entregar", args=[consulta.pk]), {
            f"accion-{medicamento.pk}": "entregar", "concepto": Movimiento.Concepto.VENTA,
        })
        self.assertContains(respuesta, "Stock insuficiente")
        medicamento.refresh_from_db()
        self.assertEqual(medicamento.estado, Estado.POR_ENTREGAR)
        self.assertEqual(services.disponible(self.acetaminofen), 26)

    def test_lo_compra_afuera(self):
        consulta = self.receta_con_acetaminofen()
        medicamento = consulta.medicamentos.get(estado=Estado.POR_ENTREGAR)
        self.entrar(self.recepcion)
        self.client.post(reverse("consultas:entregar", args=[consulta.pk]), {
            f"accion-{medicamento.pk}": "afuera", "concepto": Movimiento.Concepto.VENTA,
        })
        medicamento.refresh_from_db()
        self.assertEqual(medicamento.estado, Estado.AFUERA)
        self.assertEqual(services.disponible(self.acetaminofen), 26)

    def test_no_se_entrega_dos_veces(self):
        consulta = self.receta_con_acetaminofen(cantidad=1)
        medicamento = consulta.medicamentos.get(estado=Estado.POR_ENTREGAR)
        entregas.entregar(medicamento, usuario=self.recepcion)
        with self.assertRaises(Exception):
            entregas.entregar(medicamento, usuario=self.recepcion)
        self.assertEqual(Movimiento.objects.filter(tipo=Movimiento.Tipo.SALIDA).count(), 1)

    # ---- Editar ----

    def test_editar_no_toca_lo_ya_entregado(self):
        consulta = self.receta_con_acetaminofen(cantidad=1)
        entregas.entregar(consulta.medicamentos.get(estado=Estado.POR_ENTREGAR), usuario=self.recepcion)
        self.entrar(self.medica)
        respuesta = self.client.get(reverse("consultas:editar", args=[consulta.pk]))
        self.assertContains(respuesta, "Ya entregados (no se pueden cambiar)")
        # En el formulario solo queda el que se compra afuera
        self.assertEqual(respuesta.context["formset"].initial_form_count(), 1)

    def test_solo_el_medico_que_atendio_edita(self):
        consulta = self.receta_con_acetaminofen()
        self.entrar(self.medico_2)
        self.assertEqual(self.client.get(reverse("consultas:editar", args=[consulta.pk])).status_code, 403)
        self.assertEqual(self.client.get(consulta.get_absolute_url()).status_code, 200)  # pero sí la puede leer

    # ---- Quién puede qué ----

    def test_permisos_por_rol(self):
        consulta = self.receta_con_acetaminofen()
        urls = {
            "atender": reverse("consultas:atender", args=[self.cita.pk]),
            "detalle": consulta.get_absolute_url(),
            "lista": reverse("consultas:lista"),
            "receta": reverse("consultas:receta", args=[consulta.pk]),
            "por_entregar": reverse("consultas:por_entregar"),
            "entregar": reverse("consultas:entregar", args=[consulta.pk]),
        }
        esperado = {  # atender (302 = ya existe, lleva a la consulta), detalle, lista, receta, por_entregar, entregar
            self.medica: (302, 200, 200, 200, 403, 403),
            self.recepcion: (403, 403, 403, 200, 200, 200),
            self.admin: (403, 200, 200, 200, 200, 200),
        }
        for usuario, codigos in esperado.items():
            self.entrar(usuario)
            for (nombre, url), codigo in zip(urls.items(), codigos):
                with self.subTest(usuario=usuario.username, pantalla=nombre):
                    self.assertEqual(self.client.get(url).status_code, codigo)
        self.client.logout()
        self.assertIn(reverse("login"), self.client.get(urls["lista"])["Location"])

    def test_la_receta_impresa_no_lleva_el_diagnostico(self):
        consulta = self.receta_con_acetaminofen()
        self.entrar(self.recepcion)
        receta = self.client.get(reverse("consultas:receta", args=[consulta.pk]))
        self.assertContains(receta, "Acetaminofén (tableta 500 mg)")
        self.assertContains(receta, "1 tableta cada 8 horas por 3 días")
        self.assertContains(receta, "Ana López")
        self.assertNotContains(receta, "Faringitis")

    # ---- Integración con el resto del sistema ----

    def test_la_cita_y_el_expediente_muestran_la_consulta(self):
        self.entrar(self.medica)
        self.assertContains(self.client.get(self.cita.get_absolute_url()),
                            reverse("consultas:atender", args=[self.cita.pk]))
        self.assertContains(self.client.get(reverse("inicio")), reverse("consultas:atender", args=[self.cita.pk]))
        consulta = self.receta_con_acetaminofen()
        self.assertContains(self.client.get(self.cita.get_absolute_url()), consulta.get_absolute_url())
        expediente = self.client.get(self.paciente.get_absolute_url())
        self.assertContains(expediente, "Faringitis aguda")
        self.assertContains(expediente, reverse("consultas:nueva", args=[self.paciente.pk]))
        # Recepción no ve las consultas en el expediente
        self.entrar(self.recepcion)
        self.assertNotContains(self.client.get(self.paciente.get_absolute_url()), "Faringitis aguda")

    def test_lista_del_medico(self):
        self.receta_con_acetaminofen()
        otra = crear_paciente(nombres="Rosa", primer_apellido="Martínez", numero_documento=DUI_1)
        Consulta.objects.create(paciente=otra, medico=self.medico_2, motivo="Control", diagnostico="Sano")
        respuesta = self.client.get(reverse("consultas:lista"))  # sigue como la Dra. López
        self.assertEqual(respuesta.context["ver"], "mias")
        self.assertEqual(len(respuesta.context["pagina"]), 1)
        self.assertEqual(len(self.client.get(reverse("consultas:lista"), {"ver": "todas"}).context["pagina"]), 2)
        self.assertEqual(len(self.client.get(reverse("consultas:lista"), {"ver": "todas", "q": "rosa"}).context["pagina"]), 1)

    def test_los_datos_de_salud_se_guardan_cifrados(self):
        consulta = self.receta_con_acetaminofen()
        with connection.cursor() as cursor:
            cursor.execute("SELECT diagnostico, sintomas FROM consultas_consulta WHERE id = %s", [consulta.pk])
            diagnostico, sintomas = cursor.fetchone()
            cursor.execute("SELECT dosis, nombre FROM consultas_medicamentorecetado WHERE consulta_id = %s "
                           "AND producto_id IS NULL", [consulta.pk])
            dosis, nombre = cursor.fetchone()
        for valor in (diagnostico, sintomas, dosis, nombre):
            self.assertTrue(valor.startswith(PREFIJO_FERNET))
        self.assertEqual(Consulta.objects.get().diagnostico, "Faringitis aguda")
