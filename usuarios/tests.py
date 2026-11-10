from django.test import TestCase
from django.urls import reverse

from .models import Usuario


class PerfilRecepcionTests(TestCase):
    def setUp(self):
        self.perfil = reverse("usuarios:perfil")
        self.secretaria = Usuario.objects.create_user(
            username="recepcion",
            first_name="Elena",
            last_name="López",
            email="recepcion@example.com",
        )

    def test_perfil_requiere_iniciar_sesion(self):
        respuesta = self.client.get(self.perfil)
        self.assertRedirects(respuesta, f"{reverse('login')}?next={self.perfil}")

    def test_recepcion_ve_sus_datos_desde_el_menu(self):
        otra_cuenta = Usuario.objects.create_user("otra-cuenta", email="otra@example.com")
        self.client.force_login(self.secretaria)
        self.assertContains(self.client.get(reverse("inicio")), f'href="{self.perfil}"')

        respuesta = self.client.get(self.perfil, {"usuario": otra_cuenta.pk})
        self.assertContains(respuesta, "Elena López")
        self.assertContains(respuesta, self.secretaria.username)
        self.assertContains(respuesta, self.secretaria.email)
        self.assertContains(respuesta, "Recepción")
        self.assertNotContains(respuesta, otra_cuenta.email)

    def test_perfil_sin_nombre_ni_correo(self):
        usuario = Usuario.objects.create_user("sin-nombre")
        self.client.force_login(usuario)
        respuesta = self.client.get(self.perfil)
        self.assertContains(respuesta, "sin-nombre")
        self.assertContains(respuesta, "Sin correo registrado")

    def test_otros_roles_no_tienen_acceso_al_perfil_de_recepcion(self):
        for rol in (Usuario.Rol.MEDICO, Usuario.Rol.ADMINISTRADOR):
            with self.subTest(rol=rol):
                usuario = Usuario.objects.create_user(rol.value.lower(), rol=rol)
                self.client.force_login(usuario)
                self.assertNotContains(self.client.get(reverse("inicio")), f'href="{self.perfil}"')
                self.assertEqual(self.client.get(self.perfil).status_code, 403)
