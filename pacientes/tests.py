from datetime import date, timedelta

from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import PacienteForm
from .models import (
    Departamento,
    Distrito,
    HistorialClinico,
    Municipio,
    Paciente,
    edad_en_texto,
    normalizar_busqueda,
)
from .validators import (
    dui_es_valido,
    normalizar_dui,
    normalizar_telefono,
    validar_dui,
    validar_telefono,
)


def dui_con_verificador(cuerpo):
    """Arma un DUI válido a partir de sus 8 primeros dígitos."""
    suma = sum(int(d) * (9 - i) for i, d in enumerate(cuerpo))
    return f"{cuerpo}-{(10 - suma % 10) % 10}"


def hace_anios(anios, dias_extra=0):
    hoy = timezone.localdate()
    return date(hoy.year - anios, hoy.month, min(hoy.day, 28)) - timedelta(days=dias_extra)


DUI_1 = "01234567-8"
DUI_2 = dui_con_verificador("04567891")


def datos_formulario(**cambios):
    distrito = Distrito.objects.select_related("municipio").get(
        nombre="San Salvador", municipio__nombre="San Salvador Centro"
    )
    datos = {
        "tipo_documento": "DUI",
        "numero_documento": DUI_1,
        "nombres": "María José",
        "primer_apellido": "Pérez",
        "segundo_apellido": "López",
        "apellido_casada": "",
        "conocido_por": "",
        "sexo": "F",
        "fecha_nacimiento": hace_anios(35).isoformat(),
        "nacionalidad": "SV",
        "pais_origen": "",
        "estado_civil": "CASADO",
        "ocupacion": "Maestra",
        "departamento": distrito.municipio.departamento_id,
        "municipio": distrito.municipio_id,
        "distrito": distrito.pk,
        "area": "U",
        "direccion": "Colonia Escalón, calle El Mirador #123",
        "punto_referencia": "",
        "telefono": "7123-4567",
        "telefono_alterno": "",
        "correo": "",
        "afiliacion": "NINGUNA",
        "numero_afiliacion": "",
        "nombre_madre": "",
        "nombre_padre": "",
        "responsable_nombre": "",
        "responsable_parentesco": "",
        "responsable_dui": "",
        "responsable_telefono": "",
        "datos_proporcionados_por": "",
        "observaciones": "",
        "consentimiento_datos": "on",
        "historial-tipo_sangre": "O+",
        "historial-alergias": "Penicilina",
        "historial-enfermedades_cronicas": "",
        "historial-medicamentos_actuales": "",
        "historial-antecedentes_personales": "",
        "historial-antecedentes_familiares": "",
    }
    datos.update(cambios)
    return datos


def crear_paciente(**campos):
    distrito = Distrito.objects.get(nombre="Santa Tecla")
    valores = {
        "tipo_documento": "DUI",
        "numero_documento": DUI_2,
        "nombres": "Juan Carlos",
        "primer_apellido": "Hernández",
        "sexo": "M",
        "fecha_nacimiento": hace_anios(40),
        "distrito": distrito,
        "area": "U",
        "direccion": "Residencial Las Palmas, pasaje 3, casa 10",
        "telefono": "2222-3333",
        "consentimiento_datos": True,
    }
    valores.update(campos)
    return Paciente.objects.create(**valores)


class ValidadoresTests(TestCase):
    def test_dui_valido_con_y_sin_guion(self):
        self.assertTrue(dui_es_valido("01234567-8"))
        self.assertTrue(dui_es_valido("012345678"))
        self.assertTrue(dui_es_valido("00016297-5"))
        self.assertTrue(dui_es_valido(dui_con_verificador("98765432")))

    def test_dui_con_verificador_incorrecto(self):
        self.assertFalse(dui_es_valido("01234567-9"))
        with self.assertRaises(ValidationError):
            validar_dui("01234567-9")

    def test_dui_con_formato_incorrecto(self):
        for valor in ("1234567-8", "0123456789", "ABCDEFGH-1", "00000000-0"):
            self.assertFalse(dui_es_valido(valor), valor)

    def test_normalizar_dui(self):
        self.assertEqual(normalizar_dui(" 012345678 "), "01234567-8")

    def test_telefonos_de_el_salvador(self):
        for valor in ("2222-3333", "71234567", "6123 4567", "+503 7123-4567"):
            validar_telefono(valor)
        for valor in ("5123-4567", "7123-456", "8123-4567"):
            with self.assertRaises(ValidationError, msg=valor):
                validar_telefono(valor)
        self.assertEqual(normalizar_telefono("+503 7123 4567"), "7123-4567")


class TerritorioTests(TestCase):
    def test_division_territorial_2024(self):
        self.assertEqual(Departamento.objects.count(), 14)
        self.assertEqual(Municipio.objects.count(), 44)
        self.assertEqual(Distrito.objects.count(), 262)

    def test_distrito_pertenece_a_su_municipio_y_departamento(self):
        distrito = Distrito.objects.get(nombre="Ciudad Delgado")
        self.assertEqual(distrito.municipio.nombre, "San Salvador Centro")
        self.assertEqual(distrito.municipio.departamento.nombre, "San Salvador")


class PacienteModeloTests(TestCase):
    def test_al_registrar_se_crea_el_expediente(self):
        paciente = crear_paciente()
        historial = HistorialClinico.objects.get(paciente=paciente)
        anio = timezone.localdate().year
        self.assertEqual(historial.numero_expediente, f"{anio}-{paciente.pk:06d}")
        self.assertEqual(paciente.numero_expediente, historial.numero_expediente)

    def test_nombre_completo_con_apellido_de_casada(self):
        paciente = crear_paciente(
            nombres="Ana María", primer_apellido="López", segundo_apellido="Rivas", apellido_casada="de Pérez"
        )
        self.assertEqual(paciente.apellido_casada, "Pérez")
        self.assertEqual(paciente.nombre_completo, "Ana María López Rivas de Pérez")

    def test_clave_del_dui_no_depende_del_guion(self):
        con_guion = Paciente.calcular_clave_documento("DUI", "01234567-8")
        sin_guion = Paciente.calcular_clave_documento("DUI", "012345678")
        self.assertEqual(con_guion, sin_guion)

    def test_varios_pacientes_sin_documento(self):
        # En SQL Server el índice único filtrado debe permitir varios NULL
        crear_paciente(tipo_documento="NINGUNO", numero_documento="", observaciones="Emergencia")
        crear_paciente(tipo_documento="NINGUNO", numero_documento="", observaciones="Emergencia", nombres="Pedro")
        self.assertEqual(Paciente.objects.filter(documento_clave__isnull=True).count(), 2)

    def test_texto_de_busqueda_sin_tildes(self):
        paciente = crear_paciente(nombres="José Ángel", primer_apellido="Peña")
        self.assertIn("jose angel", paciente.texto_busqueda)
        self.assertIn("pena", paciente.texto_busqueda)
        self.assertEqual(normalizar_busqueda("  MARÍA   Núñez "), "maria nunez")

    def test_edad_en_texto(self):
        hoy = date(2026, 9, 29)
        self.assertEqual(edad_en_texto(date(2026, 9, 20), hoy), "9 días")
        self.assertEqual(edad_en_texto(date(2026, 4, 29), hoy), "5 meses")
        self.assertEqual(edad_en_texto(date(2025, 8, 29), hoy), "1 año 1 mes")
        self.assertEqual(edad_en_texto(date(1990, 10, 1), hoy), "35 años")

    def test_fecha_de_consentimiento(self):
        paciente = crear_paciente()
        self.assertIsNotNone(paciente.fecha_consentimiento)


class PacienteFormTests(TestCase):
    def formulario(self, **cambios):
        return PacienteForm(data=datos_formulario(**cambios))

    def test_formulario_valido(self):
        form = self.formulario()
        self.assertTrue(form.is_valid(), form.errors.as_json())

    def test_campos_obligatorios_vacios(self):
        form = PacienteForm(data={})
        self.assertFalse(form.is_valid())
        for campo in ("nombres", "primer_apellido", "sexo", "fecha_nacimiento", "distrito", "direccion", "telefono"):
            self.assertIn(campo, form.errors)

    def test_dui_invalido(self):
        form = self.formulario(numero_documento="01234567-9")
        self.assertFalse(form.is_valid())
        self.assertIn("numero_documento", form.errors)

    def test_adulto_salvadoreno_debe_usar_dui(self):
        form = self.formulario(tipo_documento="PASAPORTE", numero_documento="A1234567")
        self.assertFalse(form.is_valid())
        self.assertIn("tipo_documento", form.errors)

    def test_menor_no_puede_tener_dui(self):
        form = self.formulario(
            fecha_nacimiento=hace_anios(10).isoformat(),
            responsable_nombre="Rosa Pérez",
            responsable_parentesco="MADRE",
            responsable_telefono="7000-1111",
        )
        self.assertFalse(form.is_valid())
        self.assertIn("tipo_documento", form.errors)

    def test_menor_necesita_responsable(self):
        form = self.formulario(
            fecha_nacimiento=hace_anios(10).isoformat(),
            tipo_documento="PARTIDA",
            numero_documento="123-2016",
        )
        self.assertFalse(form.is_valid())
        for campo in ("responsable_nombre", "responsable_parentesco", "responsable_telefono"):
            self.assertIn(campo, form.errors)

    def test_menor_con_responsable_es_valido(self):
        form = self.formulario(
            fecha_nacimiento=hace_anios(2).isoformat(),
            tipo_documento="NUI",
            numero_documento="12345678-9",
            responsable_nombre="Rosa Pérez",
            responsable_parentesco="MADRE",
            responsable_dui="04567891-1",
            responsable_telefono="70001111",
        )
        self.assertTrue(form.is_valid(), form.errors.as_json())
        self.assertEqual(form.cleaned_data["responsable_telefono"], "7000-1111")

    def test_extranjero_necesita_pais_y_pasaporte(self):
        form = self.formulario(nacionalidad="EX")
        self.assertFalse(form.is_valid())
        self.assertIn("pais_origen", form.errors)
        self.assertIn("tipo_documento", form.errors)
        form = self.formulario(
            nacionalidad="EX", pais_origen="Honduras", tipo_documento="PASAPORTE", numero_documento="e 123456"
        )
        self.assertTrue(form.is_valid(), form.errors.as_json())

    def test_sin_documento_pide_observacion(self):
        form = self.formulario(tipo_documento="NINGUNO", numero_documento="")
        self.assertFalse(form.is_valid())
        self.assertIn("observaciones", form.errors)

    def test_fecha_de_nacimiento_futura(self):
        manana = timezone.localdate() + timedelta(days=1)
        form = self.formulario(fecha_nacimiento=manana.isoformat())
        self.assertFalse(form.is_valid())
        self.assertIn("fecha_nacimiento", form.errors)

    def test_documento_repetido(self):
        crear_paciente(numero_documento=DUI_1)
        form = self.formulario(numero_documento="012345678")
        self.assertFalse(form.is_valid())
        self.assertIn("numero_documento", form.errors)

    def test_posible_duplicado_pide_confirmacion(self):
        crear_paciente(
            tipo_documento="NINGUNO",
            numero_documento="",
            observaciones="No trajo documento",
            nombres="María José",
            primer_apellido="Pérez",
            sexo="F",
            fecha_nacimiento=hace_anios(35),
        )
        form = self.formulario(numero_documento=dui_con_verificador("11112222"))
        self.assertFalse(form.is_valid())
        self.assertIn("confirmar_no_duplicado", form.errors)
        self.assertEqual(len(form.posibles_duplicados), 1)
        form = self.formulario(
            numero_documento=dui_con_verificador("11112222"), confirmar_no_duplicado="on"
        )
        self.assertTrue(form.is_valid(), form.errors.as_json())

    def test_distrito_debe_ser_del_municipio(self):
        otro_municipio = Municipio.objects.get(nombre="Santa Ana Centro")
        form = self.formulario(municipio=otro_municipio.pk)
        self.assertFalse(form.is_valid())
        self.assertIn("distrito", form.errors)

    def test_consentimiento_obligatorio(self):
        datos = datos_formulario()
        del datos["consentimiento_datos"]
        form = PacienteForm(data=datos)
        self.assertFalse(form.is_valid())
        self.assertIn("consentimiento_datos", form.errors)


class VistasTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("secretaria", "sec@example.com", "clave-de-prueba-123")
        self.client.force_login(self.admin)

    def test_requiere_iniciar_sesion(self):
        self.client.logout()
        respuesta = self.client.get(reverse("pacientes:lista"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("login"), respuesta["Location"])

    def test_usuario_sin_permiso(self):
        usuario = User.objects.create_user("visitante", password="clave-de-prueba-123")
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(reverse("pacientes:lista")).status_code, 403)
        usuario.user_permissions.add(Permission.objects.get(codename="view_paciente"))
        self.assertEqual(self.client.get(reverse("pacientes:lista")).status_code, 200)
        self.assertEqual(self.client.get(reverse("pacientes:registrar")).status_code, 403)

    def test_registrar_paciente(self):
        respuesta = self.client.post(reverse("pacientes:registrar"), datos_formulario())
        paciente = Paciente.objects.get()
        self.assertRedirects(respuesta, paciente.get_absolute_url())
        self.assertEqual(paciente.registrado_por, self.admin)
        self.assertEqual(paciente.historial.alergias, "Penicilina")
        self.assertEqual(paciente.historial.tipo_sangre, "O+")

    def test_no_guarda_con_campos_vacios(self):
        respuesta = self.client.post(reverse("pacientes:registrar"), {})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No se pudo guardar")
        self.assertFalse(Paciente.objects.exists())

    def test_paginas_se_muestran(self):
        paciente = crear_paciente()
        for url in (
            reverse("pacientes:lista"),
            reverse("pacientes:registrar"),
            reverse("pacientes:detalle", args=[paciente.pk]),
            reverse("pacientes:editar", args=[paciente.pk]),
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_buscar_sin_tildes_por_expediente_y_por_dui(self):
        paciente = crear_paciente(nombres="María José", primer_apellido="Peña", numero_documento=DUI_1)
        otro = crear_paciente(nombres="Carlos", primer_apellido="Martínez", numero_documento=DUI_2)
        lista = reverse("pacientes:lista")
        for consulta in ("maria pena", "PEÑA", "012345678", "01234567-8", paciente.numero_expediente):
            respuesta = self.client.get(lista, {"q": consulta})
            self.assertContains(respuesta, paciente.nombre_completo, msg_prefix=consulta)
            self.assertNotContains(respuesta, otro.nombre_completo, msg_prefix=consulta)

    def test_editar_paciente(self):
        paciente = crear_paciente(numero_documento=DUI_1)
        datos = datos_formulario(telefono="2555-6666", nombres="María José", numero_documento=DUI_1)
        respuesta = self.client.post(reverse("pacientes:editar", args=[paciente.pk]), datos)
        self.assertRedirects(respuesta, paciente.get_absolute_url())
        paciente.refresh_from_db()
        self.assertEqual(paciente.telefono, "2555-6666")
        self.assertEqual(HistorialClinico.objects.filter(paciente=paciente).count(), 1)

    def test_dar_de_baja_y_reactivar(self):
        paciente = crear_paciente()
        url = reverse("pacientes:cambiar_estado", args=[paciente.pk])
        self.client.post(url)
        paciente.refresh_from_db()
        self.assertFalse(paciente.activo)
        self.assertNotContains(self.client.get(reverse("pacientes:lista")), paciente.nombre_completo)
        self.assertContains(
            self.client.get(reverse("pacientes:lista"), {"inactivos": "1"}), paciente.nombre_completo
        )
        self.client.post(url)
        paciente.refresh_from_db()
        self.assertTrue(paciente.activo)
        self.assertEqual(self.client.get(url).status_code, 405)
