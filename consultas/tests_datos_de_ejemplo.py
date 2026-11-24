"""Pruebas de los datos de ejemplo (cargar_datos_de_ejemplo) y de preparar_presentacion."""
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from citas.models import Cita
from consultas.management.commands import cargar_datos_de_ejemplo as comando
from consultas.management.commands.preparar_presentacion import es_base_de_presentacion
from consultas.models import Consulta, MedicamentoRecetado
from inventario import services
from inventario.models import Lote, Movimiento, Producto
from pacientes.models import Paciente

CLAVE = "Prueba-1234"


def cargar(**opciones):
    """Corre el comando sin escribir el archivo de credenciales en la carpeta del proyecto."""
    carpeta = tempfile.mkdtemp()
    archivo = Path(carpeta) / "credenciales.txt"
    salida = StringIO()
    with mock.patch.object(comando, "ARCHIVO_CREDENCIALES", archivo):
        call_command("cargar_datos_de_ejemplo", stdout=salida, **opciones)
    return archivo, salida.getvalue()


class DatosDeEjemploTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.archivo, cls.salida = cargar(clave=CLAVE)

    def test_usuarios_de_los_tres_roles(self):
        Usuario = get_user_model()
        roles = dict(Usuario.objects.values_list("username", "rol"))
        self.assertEqual(
            roles, {"administrador": "ADMIN", "dra.lopez": "MEDICO", "dr.martinez": "MEDICO", "recepcion": "RECEPCION"}
        )
        for usuario in Usuario.objects.all():
            self.assertTrue(usuario.check_password(CLAVE))
            self.assertFalse(usuario.debe_cambiar_clave)

    def test_credenciales_en_un_archivo(self):
        texto = self.archivo.read_text(encoding="utf-8")
        self.assertIn(f"Contraseña (la misma para todos): {CLAVE}", texto)
        self.assertIn("dra.lopez", texto)
        self.assertNotIn(CLAVE, self.salida)  # la contraseña no se muestra en la terminal
        self.assertEqual(comando.clave_guardada(self.archivo), CLAVE)

    def test_pacientes_validos_con_expediente(self):
        self.assertEqual(Paciente.objects.count(), 14)
        for paciente in Paciente.objects.all():
            paciente.full_clean()
            self.assertTrue(paciente.numero_expediente)
            self.assertLess(paciente.fecha_registro, timezone.now())
        menores = [p for p in Paciente.objects.all() if p.es_menor]
        self.assertEqual(len(menores), 3)
        self.assertTrue(all(p.responsable_nombre for p in menores))

    def test_inventario_con_avisos(self):
        self.assertEqual(Producto.objects.count(), 16)
        bajo_minimo = {p.codigo for p in Producto.objects.all() if p.bajo_minimo}
        self.assertEqual(bajo_minimo, {"MED-002", "MED-007", "INS-002"})
        self.assertTrue(Lote.objects.get(numero_lote="SR-310").vencido)
        self.assertTrue(Lote.objects.get(numero_lote="AS-031").por_vencer)
        # Lo vencido no se cuenta como disponible
        sales = Producto.objects.get(codigo="MED-009")
        self.assertEqual(services.disponible(sales), sales.stock_actual - 15)

    def test_movimientos_con_fechas_pasadas(self):
        self.assertFalse(Movimiento.objects.filter(fecha__gt=timezone.now()).exists())
        self.assertTrue(Movimiento.objects.filter(concepto=Movimiento.Concepto.VENTA, paciente__isnull=False).exists())
        self.assertTrue(Movimiento.objects.filter(concepto=Movimiento.Concepto.MERMA).exists())
        self.assertTrue(Movimiento.objects.filter(concepto=Movimiento.Concepto.DONACION).exists())

    def test_agenda_y_consultas(self):
        ahora = timezone.now()
        self.assertTrue(Cita.objects.filter(estado=Cita.Estado.NO_ASISTIO).exists())
        self.assertTrue(Cita.objects.filter(estado=Cita.Estado.CANCELADA).exists())
        proximas = Cita.objects.filter(fecha_hora__gt=ahora, estado__in=Cita.ACTIVAS)
        self.assertGreaterEqual(proximas.count(), 11)
        # Las de mañana se pueden recordar con el botón o con el comando diario
        self.assertTrue(proximas.filter(recordatorio_enviado__isnull=True).exists())
        # Toda cita atendida tiene su consulta; no hay dos citas activas del mismo médico a la misma hora
        self.assertFalse(Cita.objects.filter(estado=Cita.Estado.ATENDIDA, consulta__isnull=True).exists())
        for cita in Cita.objects.filter(estado__in=Cita.ACTIVAS):
            self.assertIsNone(cita.choque_de_horario())
        self.assertTrue(Consulta.objects.filter(cita__isnull=True).exists())
        self.assertGreaterEqual(
            MedicamentoRecetado.objects.filter(estado=MedicamentoRecetado.Estado.POR_ENTREGAR).count(), 2
        )
        self.assertTrue(MedicamentoRecetado.objects.filter(estado=MedicamentoRecetado.Estado.AFUERA).exists())

    def test_no_carga_dos_veces(self):
        with self.assertRaisesMessage(CommandError, "ya tiene pacientes"):
            cargar(clave=CLAVE)


class OpcionesDelComandoTests(TestCase):
    def test_telefono_de_todos_los_pacientes(self):
        _, salida = cargar(clave=CLAVE, telefono="+503 7123 4567")
        self.assertEqual({p.telefono for p in Paciente.objects.all()}, {"7123-4567"})
        self.assertIn("van al 7123-4567", salida)

    def test_telefono_no_valido(self):
        with self.assertRaisesMessage(CommandError, "Teléfono no válido"):
            cargar(clave=CLAVE, telefono="123")
        self.assertFalse(Paciente.objects.exists())


class PrepararPresentacionTests(TestCase):
    def test_solo_borra_la_base_de_la_presentacion(self):
        self.assertTrue(es_base_de_presentacion("clinica_presentacion"))
        self.assertFalse(es_base_de_presentacion("clinica_familiar"))
        self.assertFalse(es_base_de_presentacion("presentacion]; DROP DATABASE x; --"))
        with self.assertRaisesMessage(CommandError, "Solo se usa con la base de la presentación"):
            call_command("preparar_presentacion", sin_preguntar=True, stdout=StringIO())
