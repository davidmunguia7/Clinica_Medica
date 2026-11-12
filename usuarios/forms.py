from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from . import accesos


def _plural(cantidad, singular, plural):
    return f"{cantidad} {singular if cantidad == 1 else plural}"


class FormularioDeEntrada(AuthenticationForm):
    """El de Django, con los avisos del bloqueo por intentos fallidos."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Usuario o contraseña incorrectos. Revise que estén bien escritos e intente de nuevo.",
    }

    def get_invalid_login_error(self):
        # Para este momento el intento fallido ya quedó en la bitácora (usuarios/accesos.py)
        nombre = self.cleaned_data.get("username") or ""
        minutos = accesos.minutos_de_bloqueo(nombre)
        if minutos:
            return forms.ValidationError(
                f"Por seguridad, este usuario está bloqueado porque la contraseña se escribió mal "
                f"{accesos.INTENTOS_PERMITIDOS} veces. Intente de nuevo en {_plural(minutos, 'minuto', 'minutos')} "
                "o pida al Administrador que lo desbloquee.",
                code="bloqueado",
            )
        mensaje = self.error_messages["invalid_login"]
        quedan = accesos.intentos_restantes(nombre)
        if quedan <= 2:
            mensaje += (
                f" Le {'queda' if quedan == 1 else 'quedan'} {_plural(quedan, 'intento', 'intentos')}; "
                f"después el usuario se bloquea {accesos.MINUTOS_DE_BLOQUEO} minutos."
            )
        return forms.ValidationError(mensaje, code="invalid_login")


class FormularioCambioDeClave(PasswordChangeForm):
    """Cambiar la propia contraseña: la actual y dos veces la nueva."""

    error_messages = {
        **PasswordChangeForm.error_messages,
        "password_incorrect": "La contraseña actual no es correcta. Escríbala de nuevo.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Contraseña actual"
        self.fields["new_password1"].label = "Contraseña nueva"
        self.fields["new_password2"].label = "Repita la contraseña nueva"
        self.fields["new_password1"].help_text = ""
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "campo pr-24"  # pr-24: espacio para el botón «Mostrar»

    def full_clean(self):
        super().full_clean()
        for nombre in self.errors:
            if nombre in self.fields:
                self.fields[nombre].widget.attrs["class"] = "campo campo-error pr-24"

    def clean(self):
        datos = super().clean()
        nueva = datos.get("new_password2")
        if nueva and nueva == datos.get("old_password") and "new_password2" not in self.errors:
            self.add_error("new_password2", "La contraseña nueva tiene que ser distinta de la actual.")
        return datos
