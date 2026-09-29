"""Validaciones de documentos y teléfonos de El Salvador."""
import re

from django.core.exceptions import ValidationError

_DUI_RE = re.compile(r"^(\d{8})-?(\d)$")
_TELEFONO_RE = re.compile(r"^[267]\d{7}$")


def solo_digitos(valor):
    """Quita todo lo que no sea número: '0123 4567-8' -> '012345678'."""
    return re.sub(r"\D", "", valor or "")


def dui_es_valido(valor):
    """Indica si un DUI tiene formato 00000000-0 y un dígito verificador correcto.

    El dígito verificador se obtiene multiplicando los primeros 8 dígitos por
    9, 8, 7, 6, 5, 4, 3 y 2, sumando los resultados y calculando
    (10 - suma % 10) % 10.
    """
    coincidencia = _DUI_RE.match((valor or "").strip())
    if not coincidencia:
        return False
    cuerpo, verificador = coincidencia.groups()
    if cuerpo == "00000000":
        return False
    suma = sum(int(digito) * (9 - posicion) for posicion, digito in enumerate(cuerpo))
    return int(verificador) == (10 - suma % 10) % 10


def normalizar_dui(valor):
    """Devuelve el DUI con el formato oficial 00000000-0 cuando tiene 9 dígitos."""
    digitos = solo_digitos(valor)
    if len(digitos) == 9:
        return f"{digitos[:8]}-{digitos[8]}"
    return (valor or "").strip()


def validar_dui(valor):
    """Validador para campos que guardan un DUI."""
    if not valor:
        return
    valor = normalizar_dui(valor)
    if not _DUI_RE.match(valor):
        raise ValidationError(
            "Escriba el DUI con el formato 00000000-0 (8 dígitos, guion y 1 dígito).",
            code="dui_formato",
        )
    if not dui_es_valido(valor):
        raise ValidationError(
            "Este DUI no es válido: el último dígito no coincide. Revise que esté bien escrito.",
            code="dui_verificador",
        )


def normalizar_telefono(valor):
    """Devuelve el teléfono como 0000-0000 (quita +503, espacios y guiones)."""
    digitos = solo_digitos(valor)
    if len(digitos) == 11 and digitos.startswith("503"):
        digitos = digitos[3:]
    if len(digitos) == 8:
        return f"{digitos[:4]}-{digitos[4:]}"
    return (valor or "").strip()


def validar_telefono(valor):
    """Teléfonos de El Salvador: 8 dígitos; fijos empiezan con 2, celulares con 6 o 7."""
    if not valor:
        return
    if not _TELEFONO_RE.match(solo_digitos(normalizar_telefono(valor))):
        raise ValidationError(
            "Escriba un teléfono de 8 dígitos que empiece con 2, 6 o 7. Ej.: 7123-4567.",
            code="telefono",
        )
