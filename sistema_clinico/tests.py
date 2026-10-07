from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class InicioYSesionTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_superuser("secretaria", "sec@example.com", "clave-de-prueba-123")

    def test_inicio_pide_iniciar_sesion(self):
        respuesta = self.client.get(reverse("inicio"))
        self.assertRedirects(respuesta, f"{reverse('login')}?next=/")

    def test_pantalla_de_login(self):
        respuesta = self.client.get(reverse("login"))
        self.assertContains(respuesta, "Iniciar sesión")
        self.assertContains(respuesta, "logo-clinica-familiar.svg")

    def test_login_lleva_al_inicio(self):
        respuesta = self.client.post(
            reverse("login"), {"username": "secretaria", "password": "clave-de-prueba-123"}
        )
        self.assertRedirects(respuesta, reverse("inicio"))

    def test_login_incorrecto(self):
        respuesta = self.client.post(reverse("login"), {"username": "secretaria", "password": "mala"})
        self.assertContains(respuesta, "Usuario o contraseña incorrectos")

    def test_inicio_muestra_resumen(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("inicio"))
        self.assertContains(respuesta, "Pacientes activos")
        self.assertContains(respuesta, "Registrados hoy")
        self.assertContains(respuesta, reverse("pacientes:registrar"))

    def test_inicio_sin_permisos_no_muestra_pacientes(self):
        usuario = User.objects.create_user("visitante", password="clave-de-prueba-123")
        self.client.force_login(usuario)
        respuesta = self.client.get(reverse("inicio"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "Pacientes activos")

    def test_pagina_sin_permiso(self):
        usuario = User.objects.create_user("visitante", password="clave-de-prueba-123")
        self.client.force_login(usuario)
        respuesta = self.client.get(reverse("pacientes:lista"))
        self.assertContains(respuesta, "No tiene permiso para ver esta página", status_code=403)

    def test_salir(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("logout"))
        self.assertRedirects(respuesta, reverse("login"))
