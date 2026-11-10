from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from citas.models import Cita
from inventario.models import Producto
from pacientes.tests import DUI_1, crear_paciente
from usuarios.pruebas import sin_permisos_de_rol

User = get_user_model()
CLAVE = "clave-de-prueba-123"


class InicioYSesionTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_superuser("secretaria", "sec@example.com", CLAVE)

    def test_inicio_pide_iniciar_sesion(self):
        respuesta = self.client.get(reverse("inicio"))
        self.assertRedirects(respuesta, f"{reverse('login')}?next=/")

    def test_pantalla_de_login(self):
        respuesta = self.client.get(reverse("login"))
        self.assertContains(respuesta, "Iniciar sesión")
        self.assertContains(respuesta, "logo-clinica-familiar.svg")

    def test_login_lleva_al_inicio(self):
        respuesta = self.client.post(reverse("login"), {"username": "secretaria", "password": CLAVE})
        self.assertRedirects(respuesta, reverse("inicio"))

    def test_login_incorrecto(self):
        respuesta = self.client.post(reverse("login"), {"username": "secretaria", "password": "mala"})
        self.assertContains(respuesta, "Usuario o contraseña incorrectos")

    def test_salir(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("logout"))
        self.assertRedirects(respuesta, reverse("login"))


def hoy_a_las(hora, minuto=0):
    return timezone.make_aware(datetime.combine(timezone.localdate(), time(hora, minuto)))


class InicioPorRolTests(TestCase):
    """Al entrar, cada rol llega a su propia pantalla de inicio."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("direccion", password=CLAVE, rol="ADMIN", first_name="Marta")
        cls.medica = User.objects.create_user(
            "dra.lopez", password=CLAVE, rol="MEDICO", first_name="Ana", last_name="López"
        )
        cls.medico_2 = User.objects.create_user("dr.ramos", password=CLAVE, rol="MEDICO")
        cls.recepcion = User.objects.create_user("secretaria", password=CLAVE, rol="RECEPCION")

        cls.juan = crear_paciente()
        cls.rosa = crear_paciente(nombres="Rosa", primer_apellido="Martínez", numero_documento=DUI_1)
        historial = cls.juan.historial
        historial.alergias = "Penicilina"
        historial.save()

        cita = Cita.objects.create
        cls.cita_juan = cita(paciente=cls.juan, medico=cls.medica, fecha_hora=hoy_a_las(9), motivo="Control de presión")
        cita(paciente=cls.rosa, medico=cls.medica, fecha_hora=hoy_a_las(8),
             motivo="Dolor de garganta", estado=Cita.Estado.ATENDIDA)
        cita(paciente=cls.rosa, medico=cls.medico_2, fecha_hora=hoy_a_las(10), motivo="Vacuna")
        cita(paciente=cls.rosa, fecha_hora=hoy_a_las(11), motivo="Curación")  # sin médico asignado
        cita(paciente=cls.juan, medico=cls.medica, fecha_hora=hoy_a_las(9) + timedelta(days=2), motivo="Resultados")
        cita(paciente=cls.juan, medico=cls.medica, fecha_hora=hoy_a_las(9) + timedelta(days=30), motivo="Muy lejos")
        Producto.objects.create(codigo="MED-001", nombre="Acetaminofén", stock_minimo=10)

    def inicio(self, usuario):
        self.client.force_login(usuario)
        return self.client.get(reverse("inicio"))

    def test_recepcion(self):
        respuesta = self.inicio(self.recepcion)
        self.assertTemplateUsed(respuesta, "inicio/recepcion.html")
        self.assertContains(respuesta, "Recepción")
        for texto in ("Pacientes activos", "Registrados hoy", "Citas de hoy", "Inventario de medicamentos",
                      "Avisos del inventario", "Acetaminofén"):
            self.assertContains(respuesta, texto)
        for nombre in ("pacientes:registrar", "citas:nueva", "citas:agenda", "inventario:producto_lista",
                       "inventario:panel", "reportes:mensual"):
            self.assertContains(respuesta, reverse(nombre))
        # Ve la agenda de todos los médicos
        self.assertEqual(len(respuesta.context["citas_hoy"]), 4)
        self.assertEqual(respuesta.context["citas_hoy_pendientes"], 3)
        self.assertEqual(respuesta.context["total_pacientes"], 2)
        self.assertEqual(respuesta.context["inventario"]["total_reabastecer"], 1)
        self.assertNotContains(respuesta, reverse("usuarios:lista"))

    def test_medico(self):
        respuesta = self.inicio(self.medica)
        self.assertTemplateUsed(respuesta, "inicio/medico.html")
        self.assertContains(respuesta, ", Ana</h1>")
        # Solo sus citas: ni las del otro médico ni las que no tienen médico
        self.assertEqual([c.motivo for c in respuesta.context["citas_hoy"]],
                         ["Dolor de garganta", "Control de presión"])
        self.assertEqual(respuesta.context["citas_hoy_pendientes"], 1)
        self.assertEqual(respuesta.context["citas_hoy_atendidas"], 1)
        self.assertEqual(respuesta.context["citas_sin_medico"], 1)
        self.assertNotContains(respuesta, "Vacuna")
        # El siguiente paciente, con sus alergias a la vista
        self.assertEqual(respuesta.context["siguiente"], self.cita_juan)
        self.assertContains(respuesta, "Siguiente paciente")
        self.assertContains(respuesta, "Penicilina")
        self.assertContains(respuesta, self.juan.get_absolute_url())
        # Los próximos 7 días (la cita de dentro de un mes no entra)
        self.assertEqual([c.motivo for c in respuesta.context["proximas"]], ["Resultados"])
        self.assertContains(respuesta, f"{reverse('citas:agenda')}?medico={self.medica.pk}")
        # No registra pacientes ni ve usuarios
        self.assertNotContains(respuesta, reverse("pacientes:registrar"))
        self.assertNotContains(respuesta, reverse("usuarios:lista"))

    def test_medico_sin_citas(self):
        respuesta = self.inicio(self.medico_2)
        self.assertEqual(respuesta.context["citas_hoy_pendientes"], 1)
        self.client.post(reverse("citas:cambiar_estado", args=[respuesta.context["siguiente"].pk]),
                         {"estado": Cita.Estado.ATENDIDA})
        respuesta = self.client.get(reverse("inicio"))
        self.assertIsNone(respuesta.context["siguiente"])
        self.assertContains(respuesta, "No tiene pacientes por atender hoy.")
        self.assertContains(respuesta, "No tiene citas en los próximos 7 días.")

    def test_administrador(self):
        respuesta = self.inicio(self.admin)
        self.assertTemplateUsed(respuesta, "inicio/administrador.html")
        self.assertContains(respuesta, "Administrador")
        # Los números del mes son los mismos del reporte
        self.assertEqual([fila["nombre"] for fila in respuesta.context["resumen_mes"]],
                         ["Citas atendidas", "Pacientes nuevos", "Compras", "Ventas"])
        self.assertEqual(respuesta.context["resumen_mes"][0]["actual"], 1)
        # El equipo con sus roles
        self.assertContains(respuesta, "Equipo de la clínica")
        self.assertContains(respuesta, "Ana López")
        self.assertEqual(respuesta.context["total_usuarios"], 4)
        self.assertEqual([rol["cantidad"] for rol in respuesta.context["usuarios_por_rol"]], [1, 2, 1])
        self.assertEqual(len(respuesta.context["citas_hoy"]), 4)
        for nombre in ("usuarios:lista", "reportes:mensual", "admin:index", "admin:usuarios_usuario_add",
                       "inventario:panel"):
            self.assertContains(respuesta, reverse(nombre))

    def test_superusuario_ve_el_inicio_de_su_rol(self):
        jefe = User.objects.create_superuser("jefe", "jefe@example.com", CLAVE)
        self.assertTemplateUsed(self.inicio(jefe), "inicio/administrador.html")
        jefe.rol = "MEDICO"  # p. ej. el médico dueño de la clínica
        jefe.save()
        self.assertTemplateUsed(self.inicio(jefe), "inicio/medico.html")

    @sin_permisos_de_rol()
    def test_inicio_sin_permisos_no_muestra_datos(self):
        respuesta = self.inicio(self.recepcion)
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "Pacientes activos")
        self.assertNotContains(respuesta, "Citas de hoy")
        self.assertNotIn("citas_hoy", respuesta.context)
