"""Cifrado de datos sensibles con Fernet (biblioteca «cryptography»).

Fernet usa AES-128 en modo CBC y una firma HMAC-SHA256: además de ocultar el dato,
detecta si alguien lo alteró en la base de datos. Cada vez que se cifra el mismo
texto el resultado es distinto (lleva un valor aleatorio), así que en la base de
datos no se puede saber qué pacientes comparten un dato.

Uso en un modelo:

    from sistema_clinico.cifrado import CampoCifrado
    telefono = CampoCifrado("teléfono", max_length=9)

El valor se guarda cifrado y al leerlo vuelve en texto normal. Lo único que NO se
puede hacer es filtrar por un campo cifrado (filter(telefono=...)), porque el texto
cifrado cambia cada vez. Para buscar por documento se guarda aparte una «huella»
(HMAC-SHA256), que siempre es igual para el mismo dato pero no permite recuperarlo.

La clave va en el archivo .env, nunca en el código ni en la base de datos:

    CLAVE_CIFRADO=<se genera con: python manage.py generar_clave_cifrado>

Para cambiar la clave se ponen varias separadas por coma (la primera cifra; todas
descifran) y luego se corre «python manage.py recifrar_datos».
"""
import base64
import hashlib
import hmac
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django import forms
from django.conf import settings
from django.core import validators
from django.core.exceptions import ImproperlyConfigured
from django.db import models

# Todo texto cifrado con Fernet empieza así (byte de versión 0x80 + fecha en base64).
# Sirve para distinguir datos cifrados de datos viejos que aún están en texto normal.
PREFIJO_FERNET = "gAAAAA"


class ErrorDeCifrado(ImproperlyConfigured):
    """La clave del .env no sirve para descifrar los datos guardados."""


def clave_de_desarrollo():
    """Clave fija derivada de SECRET_KEY. Solo se usa en desarrollo si falta CLAVE_CIFRADO."""
    resumen = hashlib.sha256(f"clave-desarrollo:{settings.SECRET_KEY}".encode()).digest()
    return base64.urlsafe_b64encode(resumen).decode()


def claves():
    """Claves en orden: la primera cifra; todas sirven para descifrar."""
    configuradas = [
        clave.strip()
        for clave in (getattr(settings, "CLAVE_CIFRADO", "") or "").split(",")
        if clave.strip()
    ]
    permitir_desarrollo = getattr(settings, "CIFRADO_PERMITIR_CLAVE_DESARROLLO", False)
    if not configuradas and not permitir_desarrollo:
        raise ImproperlyConfigured(
            "Falta CLAVE_CIFRADO en el archivo .env. Genere una con "
            "«python manage.py generar_clave_cifrado --guardar»."
        )
    if permitir_desarrollo:
        desarrollo = clave_de_desarrollo()
        if desarrollo not in configuradas:
            # Al final: solo descifra lo que se guardó antes de poner una clave real.
            configuradas.append(desarrollo)
    return tuple(configuradas)


@lru_cache(maxsize=8)
def _fernet(lista_claves):
    try:
        return MultiFernet([Fernet(clave.encode()) for clave in lista_claves])
    except (ValueError, TypeError) as error:
        raise ImproperlyConfigured(
            "CLAVE_CIFRADO no es una clave Fernet válida (32 bytes en base64). "
            "Genere una con «python manage.py generar_clave_cifrado»."
        ) from error


def fernet():
    return _fernet(claves())


def esta_cifrado(valor):
    return isinstance(valor, str) and valor.startswith(PREFIJO_FERNET)


def cifrar(texto):
    """Texto normal -> texto cifrado. Las cadenas vacías y None se guardan tal cual."""
    if texto is None or texto == "":
        return texto
    return fernet().encrypt(str(texto).encode("utf-8")).decode("ascii")


def descifrar(valor):
    """Texto cifrado -> texto normal. Un dato viejo sin cifrar se devuelve tal cual."""
    if not esta_cifrado(valor):
        return valor
    try:
        return fernet().decrypt(valor.encode("ascii")).decode("utf-8")
    except InvalidToken as error:
        raise ErrorDeCifrado(
            "No se pudo descifrar un dato guardado: la CLAVE_CIFRADO del .env no es la "
            "misma con la que se cifró. Revise el .env (si cambió la clave, ponga la nueva "
            "primero y la anterior después, separadas por coma)."
        ) from error


def huella(texto):
    """HMAC-SHA256 del texto: igual para el mismo dato, pero no permite recuperarlo.

    Se usa para buscar y para evitar duplicados sin guardar el dato en claro.
    Depende de la clave principal: si la clave cambia, «recifrar_datos» la recalcula.
    """
    if not texto:
        return None
    clave = hashlib.sha256(f"huella:{claves()[0]}".encode()).digest()
    return hmac.new(clave, str(texto).encode("utf-8"), hashlib.sha256).hexdigest()


class CampoCifrado(models.TextField):
    """Campo de texto que se guarda cifrado con Fernet y se lee descifrado.

    max_length limita lo que se escribe en el formulario (en la base de datos el texto
    cifrado ocupa más). Por defecto el formulario muestra una línea; con
    multilinea=True muestra un área de texto.
    """

    description = "Texto cifrado con Fernet"

    def __init__(self, *args, multilinea=False, **kwargs):
        self.multilinea = multilinea
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        nombre, ruta, args, kwargs = super().deconstruct()
        if self.multilinea:
            kwargs["multilinea"] = True
        return nombre, ruta, args, kwargs

    def from_db_value(self, value, expression, connection):
        return descifrar(value)

    def to_python(self, value):
        return descifrar(super().to_python(value))

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if esta_cifrado(value):
            return value
        return cifrar(value)

    def formfield(self, **kwargs):
        if not self.multilinea and not self.choices:
            kwargs.setdefault("widget", forms.TextInput)
        return super().formfield(**kwargs)


class CorreoCifrado(CampoCifrado):
    """Correo electrónico cifrado (valida el formato como EmailField)."""

    default_validators = [validators.validate_email]
    description = "Correo electrónico cifrado con Fernet"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_length", 254)
        super().__init__(*args, **kwargs)

    def formfield(self, **kwargs):
        kwargs.setdefault("form_class", forms.EmailField)
        kwargs.setdefault("widget", forms.EmailInput)
        return super().formfield(**kwargs)
