"""Envío de mensajes de texto (SMS).

El proveedor se elige en settings.SMS_BACKEND:

- citas.sms.BackendSimulado (por defecto): no envía nada; el mensaje se guarda en el
  sistema como «Simulado» y se muestra en la consola donde corre el servidor.
- citas.sms.BackendTwilio: lo envía de verdad con la API de Twilio. Necesita en el .env
  TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN y TWILIO_NUMERO.

Para usar otro proveedor basta con escribir una clase con el método enviar(telefono, texto)
que devuelva un ResultadoSMS, y ponerla en SMS_BACKEND.
"""
import base64
import json
import logging
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from pacientes.validators import solo_digitos

logger = logging.getLogger(__name__)


@dataclass
class ResultadoSMS:
    estado: str  # valores de MensajeSMS.Estado
    proveedor: str
    id_externo: str = ""
    error: str = ""


def telefono_internacional(telefono):
    """'7123-4567' -> '+50371234567' (El Salvador, +503)."""
    digitos = solo_digitos(telefono)
    if len(digitos) == 8:
        return f"+503{digitos}"
    return f"+{digitos}"


class BackendSimulado:
    """No envía nada: muestra el mensaje en la consola y queda guardado como «Simulado»."""

    nombre = "simulado"

    def enviar(self, telefono, texto):
        logger.info("SMS simulado para %s: %s", telefono, texto)
        print(f"[SMS simulado] Para {telefono}: {texto}")
        return ResultadoSMS(estado="SIMULADO", proveedor=self.nombre)


class BackendTwilio:
    """Envía el SMS con la API REST de Twilio (https://www.twilio.com/docs/messaging/api)."""

    nombre = "twilio"
    url = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

    def __init__(self):
        self.sid = getattr(settings, "TWILIO_ACCOUNT_SID", "")
        self.token = getattr(settings, "TWILIO_AUTH_TOKEN", "")
        self.numero = getattr(settings, "TWILIO_NUMERO", "")
        if not (self.sid and self.token and self.numero):
            raise ImproperlyConfigured(
                "Para enviar SMS con Twilio faltan TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN o "
                "TWILIO_NUMERO en el .env."
            )

    def enviar(self, telefono, texto):
        datos = urlencode({"To": telefono, "From": self.numero, "Body": texto}).encode()
        credenciales = base64.b64encode(f"{self.sid}:{self.token}".encode()).decode()
        peticion = Request(
            self.url.format(sid=self.sid),
            data=datos,
            headers={"Authorization": f"Basic {credenciales}"},
            method="POST",
        )
        try:
            with urlopen(peticion, timeout=15) as respuesta:
                cuerpo = json.loads(respuesta.read().decode() or "{}")
        except HTTPError as error:
            detalle = error.read().decode(errors="replace")[:300]
            return ResultadoSMS("ERROR", self.nombre, error=f"Twilio respondió {error.code}: {detalle}")
        except (URLError, TimeoutError) as error:
            return ResultadoSMS("ERROR", self.nombre, error=f"No se pudo conectar con Twilio: {error}")
        return ResultadoSMS("ENVIADO", self.nombre, id_externo=cuerpo.get("sid", ""))


def obtener_backend(ruta=None):
    return import_string(ruta or settings.SMS_BACKEND)()
