"""Pruebas del inicio de sesión: entrar, bloqueo por intentos, bitácora, contraseñas e inactividad."""
import re
import time
from datetime import timedelta

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import accesos
from .middleware import ULTIMA_ACTIVIDAD
from .models import Acceso, Usuario

CLAVE = "clave-de-prueba-123"
NUEVA = "Otra-clave-segura-2026"
Rol = Usuario.Rol
Tipo = Acceso.Tipo

# Las contraseñas se revisan muchas veces: con este algoritmo las pruebas van rápido
rapido = override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])


def crear(username, rol=Rol.RECEPCION, **campos):
    return Usuario.objects.create_user(username, password=CLAVE, rol=rol, **campos)


def tipos(nombre):
    """Lo que dice la bitácora de ese usuario, del más viejo al más nuevo."""
    return list(Acceso.objects.filter(nombre_usuario__iexact=nombre).order_by("momento", "pk")
                .values_list("tipo", flat=True))


@rapido
class EntrarTests(TestCase):
    def setUp(self):
        self.medica = crear("dra.lopez", Rol.MEDICO, first_name="Ana", last_name="López")
        self.entrar_url = reverse("login")

    def entrar(self, clave=CLAVE, usuario="dra.lopez", **extra):
        return self.client.post(self.entrar_url, {"username": usuario, "password": clave}, **extra)

    def test_entra_y_queda_en_la_bitacora(self):
        respuesta = self.entrar(REMOTE_ADDR="192.168.1.20")
        self.assertRedirects(respuesta, reverse("inicio"))
        acceso = Acceso.objects.get()
        self.assertEqual((acceso.tipo, acceso.usuario, acceso.ip), (Tipo.ENTRADA, self.medica, "192.168.1.20"))

    def test_pantalla_de_entrar(self):
        respuesta = self.client.get(self.entrar_url)
        self.assertContains(respuesta, "¿Olvidó su contraseña?")
        self.assertContains(respuesta, "data-mostrar-clave")
        self.assertContains(respuesta, f"{accesos.MINUTOS_DE_BLOQUEO} minutos")

    def test_contrasena_incorrecta(self):
        respuesta = self.entrar("mala")
        self.assertContains(respuesta, "Usuario o contraseña incorrectos")
        self.assertNotIn("_auth_user_id", self.client.session)
        acceso = Acceso.objects.get()
        self.assertEqual((acceso.tipo, acceso.usuario, acceso.nombre_usuario), (Tipo.FALLIDO, self.medica, "dra.lopez"))
        self.assertEqual(accesos.intentos_restantes("dra.lopez"), 4)

    def test_avisa_cuantos_intentos_le_quedan(self):
        for _ in range(3):
            respuesta = self.entrar("mala")
        self.assertContains(respuesta, "Le quedan 2 intentos")
        respuesta = self.entrar("mala")
        self.assertContains(respuesta, "Le queda 1 intento;")

    def test_cinco_intentos_fallidos_bloquean_el_usuario(self):
        for _ in range(accesos.INTENTOS_PERMITIDOS):
            respuesta = self.entrar("mala")
        self.assertContains(respuesta, "este usuario está bloqueado")
        self.assertEqual(accesos.minutos_de_bloqueo("dra.lopez"), accesos.MINUTOS_DE_BLOQUEO)

        # Ni con la contraseña correcta entra mientras dure el bloqueo
        respuesta = self.entrar()
        self.assertContains(respuesta, "este usuario está bloqueado")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(tipos("dra.lopez"), [Tipo.FALLIDO] * 5 + [Tipo.BLOQUEO, Tipo.INTENTO_BLOQUEADO])

    def test_el_bloqueo_se_quita_solo_con_el_tiempo(self):
        for _ in range(accesos.INTENTOS_PERMITIDOS):
            self.entrar("mala")
        Acceso.objects.update(momento=timezone.now() - timedelta(minutes=accesos.MINUTOS_DE_BLOQUEO + 1))
        self.assertEqual(accesos.minutos_de_bloqueo("dra.lopez"), 0)
        self.assertRedirects(self.entrar(), reverse("inicio"))

    def test_entrar_bien_reinicia_la_cuenta(self):
        for _ in range(accesos.INTENTOS_PERMITIDOS - 1):
            self.entrar("mala")
        self.entrar()
        self.client.post(reverse("logout"))
        self.entrar("mala")
        self.assertEqual(accesos.intentos_restantes("dra.lopez"), accesos.INTENTOS_PERMITIDOS - 1)

    def test_no_importan_las_mayusculas_del_usuario(self):
        for _ in range(accesos.INTENTOS_PERMITIDOS):
            self.entrar("mala", usuario="DRA.Lopez")
        self.assertTrue(accesos.minutos_de_bloqueo("dra.lopez"))

    def test_el_bloqueo_es_solo_de_ese_usuario(self):
        crear("secretaria")
        for _ in range(accesos.INTENTOS_PERMITIDOS):
            self.entrar("mala")
        self.assertRedirects(self.entrar(usuario="secretaria"), reverse("inicio"))

    def test_usuario_que_no_existe_tambien_se_bloquea(self):
        # Así no se puede averiguar qué usuarios existen
        for _ in range(accesos.INTENTOS_PERMITIDOS):
            respuesta = self.entrar("mala", usuario="nadie")
        self.assertContains(respuesta, "este usuario está bloqueado")
        self.assertIsNone(Acceso.objects.filter(nombre_usuario="nadie").first().usuario)

    def test_el_panel_de_administracion_tambien_respeta_el_bloqueo(self):
        crear("direccion", Rol.ADMINISTRADOR)
        for _ in range(accesos.INTENTOS_PERMITIDOS):
            self.entrar("mala", usuario="direccion")
        respuesta = self.client.post(reverse("admin:login"), {"username": "direccion", "password": CLAVE,
                                                              "next": reverse("admin:index")})
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(tipos("direccion")[-1], Tipo.INTENTO_BLOQUEADO)

    def test_avisa_si_alguien_mas_intento_entrar(self):
        Acceso.objects.create(tipo=Tipo.FALLIDO, nombre_usuario="dra.lopez", ip="10.0.0.99",
                              momento=timezone.now() - timedelta(hours=2))
        respuesta = self.entrar(follow=True, REMOTE_ADDR="192.168.1.20")
        self.assertContains(respuesta, "Desde su último ingreso hubo 1 intento fallido")

    def test_no_avisa_de_sus_propios_errores_de_hace_un_momento(self):
        self.entrar("mala", REMOTE_ADDR="192.168.1.20")
        respuesta = self.entrar(follow=True, REMOTE_ADDR="192.168.1.20")
        self.assertNotContains(respuesta, "Desde su último ingreso")

    def test_usuario_desactivado_no_entra(self):
        self.medica.is_active = False
        self.medica.save()
        self.assertContains(self.entrar(), "Usuario o contraseña incorrectos")

    def test_salir_queda_en_la_bitacora(self):
        self.entrar()
        respuesta = self.client.post(reverse("logout"), follow=True)
        self.assertContains(respuesta, "Cerró su sesión")
        self.assertEqual(tipos("dra.lopez"), [Tipo.ENTRADA, Tipo.SALIDA])


@rapido
class InactividadTests(TestCase):
    def setUp(self):
        self.usuario = crear("secretaria")
        self.client.force_login(self.usuario)

    def dejar_pasar(self, minutos):
        sesion = self.client.session
        sesion[ULTIMA_ACTIVIDAD] = time.time() - minutos * 60
        sesion.save()

    def test_cierra_la_sesion_tras_los_minutos_sin_usar_el_sistema(self):
        self.client.get(reverse("inicio"))
        self.dejar_pasar(settings.SESION_MINUTOS_DE_INACTIVIDAD + 1)
        respuesta = self.client.get(reverse("pacientes:lista"), follow=True)
        self.assertRedirects(respuesta, f"{reverse('login')}?next={reverse('pacientes:lista')}")
        self.assertContains(respuesta, "su sesión se cerró porque pasaron")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(tipos("secretaria")[-1], Tipo.INACTIVIDAD)

    def test_si_la_usa_sigue_abierta(self):
        self.client.get(reverse("inicio"))
        self.dejar_pasar(settings.SESION_MINUTOS_DE_INACTIVIDAD - 1)
        self.assertEqual(self.client.get(reverse("inicio")).status_code, 200)
        self.assertLess(time.time() - self.client.session[ULTIMA_ACTIVIDAD], 60)

    def test_la_pagina_avisa_que_sigue_ahi(self):
        self.client.get(reverse("inicio"))
        self.dejar_pasar(10)
        respuesta = self.client.post(reverse("usuarios:sigo_aqui"))
        self.assertEqual(respuesta.status_code, 204)
        self.assertLess(time.time() - self.client.session[ULTIMA_ACTIVIDAD], 60)
        self.assertEqual(self.client.get(reverse("usuarios:sigo_aqui")).status_code, 405)

    def test_aviso_en_las_pantallas(self):
        respuesta = self.client.get(reverse("inicio"))
        self.assertContains(respuesta, 'id="aviso-inactividad"')
        self.assertContains(respuesta, f"var LIMITE = {settings.SESION_MINUTOS_DE_INACTIVIDAD * 60} * 1000;")
        self.client.post(reverse("logout"))
        self.assertNotContains(self.client.get(reverse("login")), 'id="aviso-inactividad"')

    def test_se_cierra_al_cerrar_el_navegador(self):
        self.assertTrue(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)


@rapido
class CambiarClaveTests(TestCase):
    def setUp(self):
        self.usuario = crear("dra.lopez", Rol.MEDICO)
        self.url = reverse("usuarios:cambiar_clave")
        self.client.force_login(self.usuario)

    def cambiar(self, actual=CLAVE, nueva=NUEVA, repetida=None):
        return self.client.post(self.url, {"old_password": actual, "new_password1": nueva,
                                           "new_password2": repetida or nueva})

    def test_todos_los_roles_la_encuentran_en_su_menu(self):
        for rol in Rol.values:
            with self.subTest(rol=rol):
                self.client.force_login(crear(f"usuario-{rol.lower()}", rol))
                self.assertContains(self.client.get(reverse("inicio")), f'href="{self.url}"')

    def test_cambia_su_contrasena_y_sigue_adentro(self):
        respuesta = self.cambiar()
        self.assertRedirects(respuesta, reverse("inicio"))
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(NUEVA))
        self.assertEqual(self.client.get(reverse("inicio")).status_code, 200)
        self.assertEqual(tipos("dra.lopez")[-1], Tipo.CAMBIO_CLAVE)

    def test_pide_la_contrasena_actual(self):
        respuesta = self.cambiar(actual="mala")
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["form"].errors["old_password"])
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(CLAVE))

    def test_la_nueva_tiene_que_ser_segura_y_distinta(self):
        for nueva, campo in (("12345678", "new_password2"), (CLAVE, "new_password2")):
            with self.subTest(nueva=nueva):
                respuesta = self.cambiar(nueva=nueva)
                self.assertIn(campo, respuesta.context["form"].errors)
        self.assertContains(self.cambiar(nueva=CLAVE), "tiene que ser distinta de la actual")
        self.assertContains(self.cambiar(repetida="Otra-distinta-2026"), "campo-error")

    def test_cierra_las_sesiones_de_otras_computadoras(self):
        otra = self.client_class()
        otra.force_login(self.usuario)
        self.cambiar()
        self.assertEqual(otra.get(reverse("inicio")).status_code, 302)


@rapido
class ContrasenaTemporalTests(TestCase):
    """El Administrador restablece la contraseña de quien la olvidó."""

    def setUp(self):
        self.admin = crear("direccion", Rol.ADMINISTRADOR, first_name="Marta")
        self.medica = crear("dra.lopez", Rol.MEDICO, first_name="Ana", last_name="López")
        self.url = reverse("usuarios:restablecer_clave", args=[self.medica.pk])

    def restablecer(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.client.logout()
        return respuesta.context["clave"]

    def test_le_da_una_temporal_que_debe_cambiar_al_entrar(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(self.url)
        clave = respuesta.context["clave"]
        self.assertRegex(clave, r"^[A-Za-z2-9]{5}-[A-Za-z2-9]{5}$")
        self.assertContains(respuesta, clave)
        self.assertContains(respuesta, "no se vuelve a mostrar")
        self.assertIn("no-store", respuesta["Cache-Control"])
        self.medica.refresh_from_db()
        self.assertTrue(self.medica.debe_cambiar_clave)
        self.assertFalse(self.medica.check_password(CLAVE))
        acceso = Acceso.objects.filter(tipo=Tipo.CLAVE_RESTABLECIDA).get()
        self.assertEqual((acceso.usuario, acceso.hecho_por), (self.medica, self.admin))

        # Entra con la temporal y no puede hacer nada hasta crear la suya
        self.client.logout()
        respuesta = self.client.post(reverse("login"), {"username": "dra.lopez", "password": clave})
        self.assertRedirects(respuesta, reverse("inicio"), target_status_code=302)
        for pantalla in (reverse("inicio"), reverse("pacientes:lista"), reverse("admin:index")):
            self.assertRedirects(self.client.get(pantalla), reverse("usuarios:cambiar_clave"))
        pagina = self.client.get(reverse("usuarios:cambiar_clave"))
        self.assertContains(pagina, "Antes de seguir, cree su propia contraseña")
        self.assertNotContains(pagina, "<nav ")  # sin menú hasta que cree la suya

        respuesta = self.client.post(reverse("usuarios:cambiar_clave"), {
            "old_password": clave, "new_password1": NUEVA, "new_password2": NUEVA,
        })
        self.assertRedirects(respuesta, reverse("inicio"))
        self.medica.refresh_from_db()
        self.assertFalse(self.medica.debe_cambiar_clave)
        self.assertEqual(self.client.get(reverse("pacientes:lista")).status_code, 200)

    def test_puede_salir_sin_cambiarla(self):
        clave = self.restablecer()
        self.client.post(reverse("login"), {"username": "dra.lopez", "password": clave})
        self.assertRedirects(self.client.post(reverse("logout")), reverse("login"))

    def test_cierra_la_sesion_que_tuviera_abierta(self):
        otra = self.client_class()
        otra.force_login(self.medica)
        self.restablecer()
        self.assertEqual(otra.get(reverse("inicio")).status_code, 302)

    def test_tambien_desbloquea(self):
        for _ in range(accesos.INTENTOS_PERMITIDOS):
            self.client.post(reverse("login"), {"username": "dra.lopez", "password": "mala"})
        clave = self.restablecer()
        respuesta = self.client.post(reverse("login"), {"username": "dra.lopez", "password": clave})
        self.assertEqual(respuesta.status_code, 302)

    def test_solo_el_administrador_y_solo_por_post(self):
        self.client.force_login(crear("secretaria"))
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.medica.refresh_from_db()
        self.assertTrue(self.medica.check_password(CLAVE))

    def test_no_la_suya_ni_la_de_un_superusuario(self):
        self.client.force_login(self.admin)
        propia = self.client.post(reverse("usuarios:restablecer_clave", args=[self.admin.pk]), follow=True)
        self.assertContains(propia, "Cambiar mi contraseña")
        jefe = Usuario.objects.create_superuser("jefe", "jefe@example.com", CLAVE)
        respuesta = self.client.post(reverse("usuarios:restablecer_clave", args=[jefe.pk]))
        self.assertEqual(respuesta.status_code, 403)
        self.admin.refresh_from_db()
        jefe.refresh_from_db()
        self.assertTrue(self.admin.check_password(CLAVE) and jefe.check_password(CLAVE))

    def test_el_panel_de_administracion_tambien_da_contrasenas_temporales(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("admin:usuarios_usuario_add"), {
            "username": "dr.ramos", "usable_password": "true", "password1": NUEVA, "password2": NUEVA,
            "first_name": "Luis", "last_name": "Ramos", "rol": Rol.MEDICO,
        })
        self.assertTrue(Usuario.objects.get(username="dr.ramos").debe_cambiar_clave)

        respuesta = self.client.post(reverse("admin:auth_user_password_change", args=[self.medica.pk]), {
            "usable_password": "true", "password1": NUEVA, "password2": NUEVA,
        })
        self.assertEqual(respuesta.status_code, 302)
        self.medica.refresh_from_db()
        self.assertTrue(self.medica.debe_cambiar_clave)
        self.assertEqual(tipos("dra.lopez")[-1], Tipo.CLAVE_RESTABLECIDA)


@rapido
class UsuariosYBitacoraTests(TestCase):
    def setUp(self):
        self.admin = crear("direccion", Rol.ADMINISTRADOR)
        self.medica = crear("dra.lopez", Rol.MEDICO, first_name="Ana", last_name="López")

    def bloquear(self, nombre="dra.lopez"):
        for _ in range(accesos.INTENTOS_PERMITIDOS):
            self.client.post(reverse("login"), {"username": nombre, "password": "mala"})

    def test_la_lista_muestra_quien_esta_bloqueado_y_lo_desbloquea(self):
        self.bloquear()
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("usuarios:lista"))
        self.assertContains(respuesta, f"Bloqueado · {accesos.MINUTOS_DE_BLOQUEO} min")
        self.assertContains(respuesta, reverse("usuarios:desbloquear", args=[self.medica.pk]))
        self.assertContains(respuesta, reverse("usuarios:restablecer_clave", args=[self.medica.pk]))
        self.assertNotContains(respuesta, reverse("usuarios:restablecer_clave", args=[self.admin.pk]))

        respuesta = self.client.post(reverse("usuarios:desbloquear", args=[self.medica.pk]), follow=True)
        self.assertContains(respuesta, "Ana López ya puede volver a entrar")
        self.assertEqual(accesos.minutos_de_bloqueo("dra.lopez"), 0)
        acceso = Acceso.objects.filter(tipo=Tipo.DESBLOQUEO).get()
        self.assertEqual(acceso.hecho_por, self.admin)

        self.client.logout()
        respuesta = self.client.post(reverse("login"), {"username": "dra.lopez", "password": CLAVE})
        self.assertRedirects(respuesta, reverse("inicio"))

    def test_recepcion_no_desbloquea(self):
        self.bloquear()
        self.client.force_login(crear("secretaria"))
        self.assertEqual(self.client.post(reverse("usuarios:desbloquear", args=[self.medica.pk])).status_code, 403)
        self.assertTrue(accesos.minutos_de_bloqueo("dra.lopez"))

    def test_bitacora(self):
        self.bloquear()
        self.client.post(reverse("login"), {"username": "direccion", "password": CLAVE})
        respuesta = self.client.get(reverse("usuarios:bitacora"))
        self.assertContains(respuesta, "Bitácora de accesos")
        self.assertContains(respuesta, "Ana López")
        self.assertContains(respuesta, "Usuario bloqueado por intentos fallidos")
        self.assertEqual(respuesta.context["fallidos_hoy"], accesos.INTENTOS_PERMITIDOS)
        self.assertEqual(respuesta.context["bloqueados_ahora"], 1)
        self.assertEqual(respuesta.context["entradas_hoy"], 1)

        solo_entradas = self.client.get(reverse("usuarios:bitacora"), {"tipo": Tipo.ENTRADA})
        self.assertEqual([a.tipo for a in solo_entradas.context["pagina"]], [Tipo.ENTRADA])
        por_nombre = self.client.get(reverse("usuarios:bitacora"), {"q": "lópez"})
        self.assertTrue(por_nombre.context["pagina"].object_list)
        self.assertTrue(all(a.nombre_usuario == "dra.lopez" for a in por_nombre.context["pagina"]))

    def test_bitacora_solo_para_el_administrador(self):
        self.client.force_login(self.medica)
        self.assertEqual(self.client.get(reverse("usuarios:bitacora")).status_code, 403)
        self.client.logout()
        self.assertIn(reverse("login"), self.client.get(reverse("usuarios:bitacora"))["Location"])

    def test_nadie_edita_ni_borra_la_bitacora(self):
        self.client.post(reverse("login"), {"username": "direccion", "password": CLAVE})
        acceso = Acceso.objects.get()
        self.assertEqual(self.client.get(reverse("admin:usuarios_acceso_changelist")).status_code, 200)
        self.assertEqual(self.client.post(reverse("admin:usuarios_acceso_delete", args=[acceso.pk]),
                                          {"post": "yes"}).status_code, 403)
        self.assertTrue(Acceso.objects.filter(pk=acceso.pk).exists())


class ClaveTemporalTests(TestCase):
    def test_formato(self):
        claves = {accesos.generar_clave_temporal() for _ in range(50)}
        self.assertEqual(len(claves), 50)
        for clave in claves:
            self.assertTrue(re.fullmatch(r"\w{5}-\w{5}", clave), clave)
            # Sin letras ni números que se confundan al dictarla (O/0, l/1/I)
            self.assertFalse(set(clave) & set("0O1lIio"), clave)
