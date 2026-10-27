import base64
from contextlib import redirect_stdout
from datetime import datetime, time, timedelta
from io import BytesIO, StringIO
from unittest import mock
from urllib.error import HTTPError
from urllib.parse import parse_qs

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from pacientes.tests import CLAVE_1, CLAVE_2, DUI_1, crear_paciente, hace_anios

from .models import Cita, MensajeSMS
from .recordatorios import (
    citas_por_recordar,
    enviar_recordatorio,
    hora_en_texto,
    telefono_de_contacto,
    texto_recordatorio,
)
from .sms import BackendSimulado, BackendTwilio, telefono_internacional

User = get_user_model()


def manana_a_las(hora, minuto=0, dias=1):
    dia = timezone.localdate() + timedelta(days=dias)
    return timezone.make_aware(datetime.combine(dia, time(hora, minuto)))


def valor_en_la_base(tabla, columna, pk):
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {columna} FROM {tabla} WHERE id = %s", [pk])
        return cursor.fetchone()[0]


class ConDatos(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.medica = User.objects.create_user(
            "dra.lopez", password="clave-de-prueba-123", first_name="Ana", last_name="López", rol="MEDICO"
        )
        cls.medico_2 = User.objects.create_user("dr.ramos", password="clave-de-prueba-123", rol="MEDICO")
        cls.paciente = crear_paciente(telefono="7123-4567")

    def cita(self, cuando, medico=None, **campos):
        valores = {"paciente": self.paciente, "medico": medico or self.medica,
                   "fecha_hora": cuando, "motivo": "Control de presión"}
        valores.update(campos)
        return Cita.objects.create(**valores)

@override_settings(CLAVE_CIFRADO=CLAVE_1)
class CitaModeloTests(ConDatos):
    def nueva(self, cuando, **campos):
        return Cita(paciente=self.paciente, medico=campos.pop("medico", self.medica),
                    fecha_hora=cuando, motivo="Chequeo", **campos)

    def test_no_se_agenda_en_el_pasado(self):
        with self.assertRaises(ValidationError) as error:
            self.nueva(timezone.now() - timedelta(hours=1)).full_clean()
        self.assertIn("fecha_hora", error.exception.message_dict)

    def test_choque_de_horario_con_el_mismo_medico(self):
        self.cita(manana_a_las(10))  # 10:00 a 10:30
        with self.assertRaises(ValidationError):
            self.nueva(manana_a_las(10, 15)).full_clean()
        self.nueva(manana_a_las(10, 30)).full_clean()  # empieza cuando termina la otra
        self.nueva(manana_a_las(10, 15), medico=self.medico_2).full_clean()  # otro médico

    def test_una_cita_cancelada_libera_el_horario(self):
        self.cita(manana_a_las(10), estado=Cita.Estado.CANCELADA)
        self.nueva(manana_a_las(10)).full_clean()

    def test_paciente_dado_de_baja(self):
        self.paciente.activo = False
        self.paciente.save()
        with self.assertRaises(ValidationError) as error:
            self.nueva(manana_a_las(9)).full_clean()
        self.assertIn("paciente", error.exception.message_dict)

    def test_se_puede_corregir_una_cita_pasada_sin_cambiar_la_hora(self):
        cita = self.cita(timezone.now() - timedelta(days=1))
        cita.notas = "Llegó tarde"
        cita.full_clean()

    def test_recifrar_tambien_cambia_la_clave_de_las_citas(self):
        with override_settings(CLAVE_CIFRADO=CLAVE_1):
            cita = self.cita(manana_a_las(8))
        with override_settings(CLAVE_CIFRADO=f"{CLAVE_2},{CLAVE_1}"):
            salida = StringIO()
            call_command("recifrar_datos", stdout=salida)
            self.assertIn("1 citas", salida.getvalue())
        with override_settings(CLAVE_CIFRADO=CLAVE_2, CIFRADO_PERMITIR_CLAVE_DESARROLLO=False):
            self.assertEqual(Cita.objects.get(pk=cita.pk).motivo, "Control de presión")

    def test_motivo_y_notas_se_guardan_cifrados(self):
        cita = self.cita(manana_a_las(8), notas="Paciente con dolor de pecho")
        self.assertTrue(valor_en_la_base("citas_cita", "motivo", cita.pk).startswith("gAAAAA"))
        self.assertTrue(valor_en_la_base("citas_cita", "notas", cita.pk).startswith("gAAAAA"))
        self.assertEqual(Cita.objects.get(pk=cita.pk).motivo, "Control de presión")


@override_settings(CLINICA_NOMBRE="Clínica Familiar", CLINICA_TELEFONO="2222-0000")
class RecordatoriosTests(ConDatos):
    def test_hora_en_texto(self):
        self.assertEqual(hora_en_texto(time(0, 5)), "12:05 a. m.")
        self.assertEqual(hora_en_texto(time(9, 30)), "9:30 a. m.")
        self.assertEqual(hora_en_texto(time(12, 0)), "12:00 p. m.")
        self.assertEqual(hora_en_texto(time(15, 45)), "3:45 p. m.")

    def test_texto_del_recordatorio(self):
        cuando = manana_a_las(9, 30)
        texto = texto_recordatorio(self.cita(cuando))
        self.assertTrue(texto.startswith("Clínica Familiar: Hola Juan,"))
        self.assertIn(f"{cuando.day}/{cuando.month} a las 9:30 a. m. con Ana López.", texto)
        self.assertIn("llame al 2222-0000", texto)

    def test_a_los_menores_se_les_avisa_al_responsable(self):
        nina = crear_paciente(nombres="Sofía", numero_documento=DUI_1, fecha_nacimiento=hace_anios(8),
                              telefono="", responsable_telefono="7999-8888")
        self.assertEqual(telefono_de_contacto(nina), "7999-8888")
        self.assertEqual(telefono_de_contacto(self.paciente), "7123-4567")

    def test_recordatorio_simulado(self):
        cita = self.cita(manana_a_las(9))
        salida = StringIO()
        with redirect_stdout(salida):
            mensaje = enviar_recordatorio(cita, backend=BackendSimulado())
        self.assertIn("[SMS simulado] Para +50371234567", salida.getvalue())
        self.assertEqual(mensaje.estado, MensajeSMS.Estado.SIMULADO)
        cita.refresh_from_db()
        self.assertIsNotNone(cita.recordatorio_enviado)
        # El teléfono y el texto quedan cifrados en la base de datos
        self.assertTrue(valor_en_la_base("citas_mensajesms", "telefono", mensaje.pk).startswith("gAAAAA"))
        self.assertEqual(MensajeSMS.objects.get(pk=mensaje.pk).telefono, "7123-4567")

    def test_paciente_sin_telefono(self):
        self.paciente.telefono = ""
        self.paciente.save()
        cita = self.cita(manana_a_las(9))
        mensaje = enviar_recordatorio(cita, backend=BackendSimulado())
        self.assertEqual(mensaje.estado, MensajeSMS.Estado.ERROR)
        cita.refresh_from_db()
        self.assertIsNone(cita.recordatorio_enviado)

    def test_que_citas_se_recuerdan(self):
        ahora = timezone.now()
        en_dos_horas = self.cita(ahora + timedelta(hours=2))
        self.cita(ahora + timedelta(hours=30), medico=self.medico_2)                    # fuera de las 24 h
        self.cita(ahora + timedelta(hours=3), estado=Cita.Estado.CANCELADA)            # cancelada
        self.cita(ahora + timedelta(hours=4), recordatorio_enviado=ahora)              # ya se avisó
        self.cita(ahora - timedelta(hours=1), medico=self.medico_2)                    # ya pasó
        self.assertEqual(list(citas_por_recordar(ahora)), [en_dos_horas])
        self.assertEqual(len(citas_por_recordar(ahora, horas=48)), 2)

    def test_comando_enviar_recordatorios(self):
        self.cita(timezone.now() + timedelta(hours=5))
        salida = StringIO()
        with redirect_stdout(StringIO()):
            call_command("enviar_recordatorios", stdout=salida)
        self.assertIn("Recordatorios: 1 enviados (simulado), 0 con error.", salida.getvalue())
        self.assertEqual(MensajeSMS.objects.count(), 1)
        # La segunda vez ya no hay nada que avisar
        salida = StringIO()
        call_command("enviar_recordatorios", stdout=salida)
        self.assertIn("No hay citas por recordar.", salida.getvalue())


class RespuestaFalsa(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@override_settings(TWILIO_ACCOUNT_SID="AC123", TWILIO_AUTH_TOKEN="token-de-prueba", TWILIO_NUMERO="+15005550006")
class TwilioTests(TestCase):
    def test_telefono_internacional(self):
        self.assertEqual(telefono_internacional("7123-4567"), "+50371234567")
        self.assertEqual(telefono_internacional("+1 (555) 123-4567"), "+15551234567")

    def test_envio_correcto(self):
        with mock.patch("citas.sms.urlopen", return_value=RespuestaFalsa(b'{"sid": "SM123"}')) as urlopen:
            resultado = BackendTwilio().enviar("+50371234567", "Hola")
        self.assertEqual((resultado.estado, resultado.id_externo), ("ENVIADO", "SM123"))
        peticion = urlopen.call_args.args[0]
        self.assertIn("/Accounts/AC123/Messages.json", peticion.full_url)
        self.assertEqual(parse_qs(peticion.data.decode())["To"], ["+50371234567"])
        esperado = base64.b64encode(b"AC123:token-de-prueba").decode()
        self.assertEqual(peticion.get_header("Authorization"), f"Basic {esperado}")

    def test_twilio_responde_error(self):
        error = HTTPError("https://api.twilio.com", 400, "Bad Request", {}, BytesIO(b'{"message": "Numero invalido"}'))
        with mock.patch("citas.sms.urlopen", side_effect=error):
            resultado = BackendTwilio().enviar("+50300000000", "Hola")
        self.assertEqual(resultado.estado, "ERROR")
        self.assertIn("400", resultado.error)

    @override_settings(TWILIO_AUTH_TOKEN="")
    def test_sin_configuracion(self):
        with self.assertRaises(ImproperlyConfigured):
            BackendTwilio()


class VistasCitasTests(ConDatos):
    def setUp(self):
        self.admin = User.objects.create_superuser("recepcion", "recepcion@example.com", "clave-de-prueba-123")
        self.client.force_login(self.admin)

    def datos(self, cuando, **cambios):
        local = timezone.localtime(cuando)
        datos = {
            "paciente": self.paciente.pk, "medico": self.medica.pk,
            "fecha_hora_0": local.date().isoformat(), "fecha_hora_1": local.strftime("%H:%M"),
            "duracion_minutos": 30, "motivo": "Dolor de cabeza", "notas": "",
        }
        datos.update(cambios)
        return datos

    def test_paginas_se_muestran(self):
        cita = self.cita(manana_a_las(11))
        for url in (
            reverse("citas:agenda"),
            reverse("citas:agenda") + f"?fecha={manana_a_las(11):%Y-%m-%d}&medico={self.medica.pk}",
            reverse("citas:nueva"),
            reverse("citas:nueva") + f"?paciente={self.paciente.pk}",
            reverse("citas:detalle", args=[cita.pk]),
            reverse("citas:editar", args=[cita.pk]),
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertContains(self.client.get(reverse("citas:agenda") + f"?fecha={manana_a_las(11):%Y-%m-%d}"),
                            "Hernández")

    def test_agendar_cita(self):
        respuesta = self.client.post(reverse("citas:nueva"), self.datos(manana_a_las(9, 30)))
        cita = Cita.objects.get()
        self.assertRedirects(respuesta, reverse("citas:detalle", args=[cita.pk]))
        self.assertEqual(cita.creada_por, self.admin)
        self.assertEqual(cita.fecha_hora, manana_a_las(9, 30))
        self.assertEqual(cita.estado, Cita.Estado.PROGRAMADA)

    def test_no_deja_agendar_en_un_horario_ocupado(self):
        self.cita(manana_a_las(9, 30))
        respuesta = self.client.post(reverse("citas:nueva"), self.datos(manana_a_las(9, 45)))
        self.assertContains(respuesta, "ya tiene una cita")
        self.assertEqual(Cita.objects.count(), 1)

    def test_cambiar_estado(self):
        cita = self.cita(manana_a_las(9))
        url = reverse("citas:cambiar_estado", args=[cita.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url, {"estado": "ATENDIDA"})
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Cita.Estado.ATENDIDA)
        # Una cita atendida ya no se puede cancelar
        respuesta = self.client.post(url, {"estado": "CANCELADA"}, follow=True)
        self.assertContains(respuesta, "no se puede hacer")
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Cita.Estado.ATENDIDA)

    def test_enviar_recordatorio_desde_la_cita(self):
        cita = self.cita(manana_a_las(9))
        with redirect_stdout(StringIO()):
            respuesta = self.client.post(reverse("citas:recordar", args=[cita.pk]), follow=True)
        self.assertContains(respuesta, "Recordatorio simulado")
        self.assertEqual(cita.mensajes.get().enviado_por, self.admin)

    def test_al_cambiar_la_hora_se_vuelve_a_recordar(self):
        cita = self.cita(manana_a_las(9), recordatorio_enviado=timezone.now())
        self.client.post(reverse("citas:editar", args=[cita.pk]), self.datos(manana_a_las(15)))
        cita.refresh_from_db()
        self.assertEqual(cita.fecha_hora, manana_a_las(15))
        self.assertIsNone(cita.recordatorio_enviado)

    def test_el_expediente_muestra_las_citas(self):
        self.cita(manana_a_las(9))
        self.cita(timezone.now() - timedelta(days=3), motivo="Fiebre", estado=Cita.Estado.ATENDIDA)
        respuesta = self.client.get(reverse("pacientes:detalle", args=[self.paciente.pk]))
        self.assertEqual(len(respuesta.context["citas_proximas"]), 1)
        self.assertEqual(len(respuesta.context["citas_anteriores"]), 1)
        self.assertContains(respuesta, "Fiebre")
        self.assertContains(respuesta, f'{reverse("citas:nueva")}?paciente={self.paciente.pk}')

    def test_permisos(self):
        usuario = User.objects.create_user("visitante", password="clave-de-prueba-123")
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(reverse("citas:agenda")).status_code, 403)
        usuario.user_permissions.add(Permission.objects.get(codename="view_cita"))
        self.assertEqual(self.client.get(reverse("citas:agenda")).status_code, 200)
        self.assertEqual(self.client.get(reverse("citas:nueva")).status_code, 403)

        self.client.logout()
        respuesta = self.client.get(reverse("citas:agenda"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("login"), respuesta["Location"])
