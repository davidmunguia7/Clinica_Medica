from django.contrib.auth.models import AnonymousUser, Permission
from django.test import TestCase
from django.urls import reverse

from . import roles
from .models import Usuario

CLAVE = "clave-de-prueba-123"
Rol = Usuario.Rol


def crear(username, rol, **campos):
    return Usuario.objects.create_user(username, password=CLAVE, rol=rol, **campos)


class RolesTests(TestCase):
    """usuarios/roles.py: qué puede hacer cada rol."""

    def test_cada_rol_tiene_su_lista(self):
        self.assertEqual(set(roles.PERMISOS_POR_ROL), set(Rol.values))
        self.assertEqual(set(roles.DESCRIPCIONES), set(Rol.values))

    def test_todos_los_permisos_existen(self):
        # Si alguien escribe mal un permiso en roles.py, esta prueba lo dice
        existentes = {
            f"{app}.{codigo}"
            for app, codigo in Permission.objects.values_list("content_type__app_label", "codename")
        }
        usados = set().union(*roles.PERMISOS_POR_ROL.values())
        usados |= {permiso for _, filas in roles.CAPACIDADES for _, permiso in filas}
        self.assertEqual(usados - existentes, set())

    def test_nadie_borra_desde_el_sistema(self):
        for rol, permisos in roles.PERMISOS_POR_ROL.items():
            self.assertEqual([p for p in permisos if ".delete_" in p], [], rol)

    def test_medico(self):
        medico = crear("dra.lopez", Rol.MEDICO)
        for permiso in ("pacientes.view_paciente", "pacientes.change_paciente", "citas.view_cita",
                        "citas.add_cita", "citas.change_cita", "inventario.view_producto"):
            self.assertTrue(medico.has_perm(permiso), permiso)
        for permiso in ("pacientes.add_paciente", "inventario.add_producto", "inventario.add_movimiento",
                        "inventario.view_movimiento", "usuarios.view_usuario"):
            self.assertFalse(medico.has_perm(permiso), permiso)

    def test_recepcion(self):
        recepcion = crear("secretaria", Rol.RECEPCION)
        for permiso in ("pacientes.add_paciente", "pacientes.change_paciente", "citas.add_cita",
                        "inventario.add_producto", "inventario.add_movimiento", "inventario.view_movimiento"):
            self.assertTrue(recepcion.has_perm(permiso), permiso)
        for permiso in ("usuarios.view_usuario", "usuarios.add_usuario", "inventario.change_categoria"):
            self.assertFalse(recepcion.has_perm(permiso), permiso)

    def test_administrador_puede_lo_de_recepcion_y_los_usuarios(self):
        admin = crear("direccion", Rol.ADMINISTRADOR)
        self.assertFalse(admin.is_superuser)
        for permiso in (*roles.permisos_del_rol(Rol.RECEPCION), "usuarios.add_usuario", "usuarios.change_usuario"):
            self.assertTrue(admin.has_perm(permiso), permiso)
        self.assertFalse(admin.has_perm("usuarios.delete_usuario"))
        self.assertTrue(admin.has_module_perms("usuarios"))
        self.assertFalse(crear("dr.ramos", Rol.MEDICO).has_module_perms("usuarios"))

    def test_el_cambio_de_rol_vale_de_inmediato(self):
        usuario = crear("ana", Rol.MEDICO)
        self.assertFalse(usuario.has_perm("pacientes.add_paciente"))
        usuario.rol = Rol.RECEPCION
        usuario.save()
        self.assertTrue(Usuario.objects.get(pk=usuario.pk).has_perm("pacientes.add_paciente"))

    def test_usuario_desactivado_o_sin_sesion_no_puede_nada(self):
        desactivado = crear("exempleado", Rol.ADMINISTRADOR, is_active=False)
        self.assertFalse(desactivado.has_perm("pacientes.view_paciente"))
        self.assertEqual(desactivado.get_all_permissions(), set())
        self.assertFalse(AnonymousUser().has_perm("pacientes.view_paciente"))

    def test_los_permisos_sueltos_se_suman_a_los_del_rol(self):
        medico = crear("dra.lopez", Rol.MEDICO)
        medico.user_permissions.add(Permission.objects.get(codename="add_paciente"))
        medico = Usuario.objects.get(pk=medico.pk)
        self.assertTrue(medico.has_perm("pacientes.add_paciente"))   # el suelto
        self.assertTrue(medico.has_perm("citas.view_cita"))          # el del rol
        self.assertIn("citas.view_cita", medico.get_all_permissions())

    def test_matriz_para_la_pantalla(self):
        matriz = roles.matriz()
        self.assertEqual([grupo["modulo"] for grupo in matriz][:2], ["Pacientes", "Citas"])
        registrar = next(f for g in matriz for f in g["filas"] if f["texto"] == "Registrar pacientes nuevos")
        self.assertEqual(registrar["celdas"], [True, False, True])  # Administrador, Médico, Recepción


class UsuarioTests(TestCase):
    def test_createsuperuser_entra_como_administrador(self):
        jefe = Usuario.objects.create_superuser("jefe", "jefe@example.com", CLAVE)
        self.assertEqual(jefe.rol, Rol.ADMINISTRADOR)
        self.assertTrue(jefe.is_staff)
        # Un superusuario puede tener otro rol si se le indica (p. ej. el médico dueño de la clínica)
        duenio = Usuario.objects.create_superuser("duenio", "d@example.com", CLAVE, rol=Rol.MEDICO)
        self.assertEqual(duenio.rol, Rol.MEDICO)
        self.assertTrue(duenio.is_staff)

    def test_solo_el_administrador_entra_al_panel_de_administracion(self):
        usuario = crear("ana", Rol.ADMINISTRADOR)
        self.assertTrue(usuario.is_staff)
        usuario.rol = Rol.RECEPCION
        usuario.save(update_fields=["rol"])
        self.assertFalse(Usuario.objects.get(pk=usuario.pk).is_staff)
        self.assertFalse(crear("dr.ramos", Rol.MEDICO, is_staff=True).is_staff)

    def test_iniciales(self):
        self.assertEqual(crear("dra.lopez", Rol.MEDICO, first_name="Ana", last_name="López").iniciales, "AL")
        self.assertEqual(crear("secretaria", Rol.RECEPCION).iniciales, "SE")

    def test_usuario_nuevo_es_de_recepcion(self):
        usuario = Usuario.objects.create_user("nuevo", password=CLAVE)
        self.assertEqual(usuario.rol, Rol.RECEPCION)
        self.assertTrue(usuario.es_recepcion)
        self.assertFalse(usuario.es_medico or usuario.es_administrador)


class PantallasPorRolTests(TestCase):
    """Cada rol entra a sus pantallas y recibe «sin permiso» (403) en las demás."""

    @classmethod
    def setUpTestData(cls):
        cls.usuarios = {
            Rol.ADMINISTRADOR: crear("direccion", Rol.ADMINISTRADOR, first_name="Marta", last_name="Díaz"),
            Rol.MEDICO: crear("dra.lopez", Rol.MEDICO, first_name="Ana", last_name="López"),
            Rol.RECEPCION: crear("secretaria", Rol.RECEPCION),
        }

    def entrar(self, rol):
        self.client.force_login(self.usuarios[rol])

    def test_quien_entra_a_que(self):
        #                                 Administrador, Médico, Recepción
        esperado = {
            "inicio":                      (200, 200, 200),
            "pacientes:lista":             (200, 200, 200),
            "pacientes:registrar":         (200, 403, 200),
            "citas:agenda":                (200, 200, 200),
            "citas:nueva":                 (200, 200, 200),
            "inventario:producto_lista":   (200, 200, 200),
            "inventario:panel":            (200, 200, 200),
            "inventario:producto_crear":   (200, 403, 200),
            "inventario:movimiento_lista": (200, 403, 200),
            "reportes:mensual":            (200, 200, 200),
            "usuarios:lista":              (200, 403, 403),
            "admin:index":                 (200, 302, 302),  # 302: lo manda a la entrada del panel
        }
        for posicion, rol in enumerate(Rol.values):
            self.entrar(rol)
            for nombre, codigos in esperado.items():
                with self.subTest(rol=rol, pantalla=nombre):
                    self.assertEqual(self.client.get(reverse(nombre)).status_code, codigos[posicion])

    def test_el_menu_cambia_con_el_rol(self):
        enlaces = {nombre: f'href="{reverse(nombre)}"' for nombre in
                   ("pacientes:lista", "citas:agenda", "inventario:producto_lista",
                    "reportes:mensual", "usuarios:lista", "pacientes:registrar")}
        self.entrar(Rol.MEDICO)
        pagina = self.client.get(reverse("pacientes:lista")).content.decode()
        for nombre in ("pacientes:lista", "citas:agenda", "inventario:producto_lista", "reportes:mensual"):
            self.assertIn(enlaces[nombre], pagina, nombre)
        for nombre in ("usuarios:lista", "pacientes:registrar"):
            self.assertNotIn(enlaces[nombre], pagina, nombre)

        self.entrar(Rol.RECEPCION)
        pagina = self.client.get(reverse("citas:agenda")).content.decode()
        self.assertIn(enlaces["pacientes:registrar"], pagina)
        self.assertNotIn(enlaces["usuarios:lista"], pagina)

        self.entrar(Rol.ADMINISTRADOR)
        self.assertIn(enlaces["usuarios:lista"], self.client.get(reverse("citas:agenda")).content.decode())

    def test_el_medico_ve_el_reporte_sin_el_dinero(self):
        self.entrar(Rol.MEDICO)
        reporte = self.client.get(reverse("reportes:mensual")).context["r"]
        self.assertIn("citas", reporte)
        self.assertIn("pacientes", reporte)
        self.assertNotIn("inventario", reporte)
        self.entrar(Rol.RECEPCION)
        self.assertIn("inventario", self.client.get(reverse("reportes:mensual")).context["r"])

    def test_sin_permiso_muestra_la_pagina_de_aviso(self):
        self.entrar(Rol.MEDICO)
        respuesta = self.client.get(reverse("pacientes:registrar"))
        self.assertContains(respuesta, "No tiene permiso para ver esta página", status_code=403)

    def test_usuarios_y_roles(self):
        self.entrar(Rol.ADMINISTRADOR)
        respuesta = self.client.get(reverse("usuarios:lista"))
        self.assertContains(respuesta, "Usuarios y roles")
        self.assertContains(respuesta, "Ana López")
        self.assertContains(respuesta, "Qué puede hacer cada rol")
        self.assertContains(respuesta, "Registrar pacientes nuevos")
        self.assertContains(respuesta, reverse("admin:usuarios_usuario_add"))
        self.assertContains(respuesta, reverse("admin:usuarios_usuario_change", args=[self.usuarios[Rol.MEDICO].pk]))
        self.assertEqual([rol["activos"] for rol in respuesta.context["roles"]], [1, 1, 1])

    def test_usuarios_y_roles_pide_iniciar_sesion(self):
        respuesta = self.client.get(reverse("usuarios:lista"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("login"), respuesta["Location"])


class PanelDeAdministracionTests(TestCase):
    """Lo que el Administrador (que no es superusuario) puede hacer con los usuarios en /admin/."""

    def setUp(self):
        self.admin = crear("direccion", Rol.ADMINISTRADOR)
        self.client.force_login(self.admin)

    def test_crea_un_usuario_con_su_rol(self):
        respuesta = self.client.post(reverse("admin:usuarios_usuario_add"), {
            "username": "dr.ramos", "usable_password": "true", "password1": CLAVE, "password2": CLAVE,
            "first_name": "Luis", "last_name": "Ramos", "rol": Rol.MEDICO,
        })
        self.assertEqual(respuesta.status_code, 302, respuesta.context and respuesta.context["adminform"].form.errors)
        nuevo = Usuario.objects.get(username="dr.ramos")
        self.assertEqual((nuevo.rol, nuevo.get_full_name()), (Rol.MEDICO, "Luis Ramos"))
        self.assertTrue(nuevo.check_password(CLAVE))
        self.assertTrue(nuevo.has_perm("citas.view_cita"))
        self.assertFalse(nuevo.is_staff)

    def test_cambia_el_rol_de_otro_usuario(self):
        otro = crear("ana", Rol.RECEPCION)
        respuesta = self.client.post(reverse("admin:usuarios_usuario_change", args=[otro.pk]), {
            "username": "ana", "first_name": "Ana", "last_name": "", "email": "",
            "rol": Rol.MEDICO, "is_active": "on",
        })
        self.assertEqual(respuesta.status_code, 302, respuesta.context and respuesta.context["adminform"].form.errors)
        self.assertEqual(Usuario.objects.get(pk=otro.pk).rol, Rol.MEDICO)

    def test_no_puede_volverse_superusuario(self):
        respuesta = self.client.post(reverse("admin:usuarios_usuario_change", args=[self.admin.pk]), {
            "username": "direccion", "first_name": "", "last_name": "", "email": "",
            "rol": Rol.ADMINISTRADOR, "is_active": "on", "is_superuser": "on",
        })
        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(Usuario.objects.get(pk=self.admin.pk).is_superuser)

    def test_no_toca_las_cuentas_de_superusuario(self):
        jefe = Usuario.objects.create_superuser("jefe", "jefe@example.com", CLAVE)
        for nombre in ("admin:usuarios_usuario_change", "admin:auth_user_password_change"):
            with self.subTest(pantalla=nombre):
                respuesta = self.client.post(reverse(nombre, args=[jefe.pk]), {"password1": "x", "password2": "x"})
                self.assertEqual(respuesta.status_code, 403)
        self.assertTrue(Usuario.objects.get(pk=jefe.pk).check_password(CLAVE))


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
