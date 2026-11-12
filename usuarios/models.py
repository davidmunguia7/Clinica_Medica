from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.utils import timezone


class UsuarioManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        # «createsuperuser» crea a quien administra el sistema: entra como Administrador
        extra_fields.setdefault("rol", Usuario.Rol.ADMINISTRADOR)
        return super().create_superuser(username, email, password, **extra_fields)


class Usuario(AbstractUser):
    class Rol(models.TextChoices):
        ADMINISTRADOR = 'ADMIN', 'Administrador'
        MEDICO = 'MEDICO', 'Médico'
        RECEPCION = 'RECEPCION', 'Recepción'

    # El rol decide qué pantallas ve cada quien y qué puede hacer (usuarios/roles.py)
    rol = models.CharField(
        max_length=20,
        choices=Rol.choices,
        default=Rol.RECEPCION,
    )
    # Se marca cuando el Administrador le da una contraseña temporal (al crear el usuario o al
    # restablecerla): al entrar, el sistema no deja hacer nada hasta que cree la suya.
    debe_cambiar_clave = models.BooleanField(
        "debe cambiar su contraseña",
        default=False,
        help_text="Al entrar, el sistema le pedirá crear su propia contraseña antes de seguir.",
    )

    objects = UsuarioManager()

    def __str__(self):
        return f"{self.username} ({self.get_rol_display()})"

    def save(self, *args, **kwargs):
        # Al panel de administración (/admin/) solo entran el Administrador y los superusuarios
        self.is_staff = self.is_superuser or self.rol == self.Rol.ADMINISTRADOR
        campos = kwargs.get("update_fields")
        if campos is not None and {"rol", "is_superuser"} & set(campos):
            kwargs["update_fields"] = {*campos, "is_staff"}
        super().save(*args, **kwargs)

    @property
    def iniciales(self):
        """Dos letras para el círculo que acompaña al nombre."""
        return (f"{self.first_name[:1]}{self.last_name[:1]}" or self.username[:2]).upper()

    @property
    def es_administrador(self):
        return self.rol == self.Rol.ADMINISTRADOR

    @property
    def es_medico(self):
        return self.rol == self.Rol.MEDICO

    @property
    def es_recepcion(self):
        return self.rol == self.Rol.RECEPCION


class Acceso(models.Model):
    """Bitácora de accesos: quién entró, quién se equivocó de contraseña, quién salió y cuándo.

    La llena usuarios/accesos.py (no se escribe a mano) y nadie la puede editar ni borrar.
    También sirve para el bloqueo por intentos fallidos.
    """

    class Tipo(models.TextChoices):
        ENTRADA = "ENTRADA", "Entró al sistema"
        FALLIDO = "FALLIDO", "Intento fallido"
        BLOQUEO = "BLOQUEO", "Usuario bloqueado por intentos fallidos"
        INTENTO_BLOQUEADO = "INTENTO_BLOQUEADO", "Intento con el usuario bloqueado"
        SALIDA = "SALIDA", "Salió del sistema"
        INACTIVIDAD = "INACTIVIDAD", "Sesión cerrada por inactividad"
        CAMBIO_CLAVE = "CAMBIO_CLAVE", "Cambió su contraseña"
        CLAVE_RESTABLECIDA = "RESTABLECIDA", "Contraseña restablecida por el Administrador"
        DESBLOQUEO = "DESBLOQUEO", "Desbloqueado por el Administrador"

    momento = models.DateTimeField("fecha y hora", default=timezone.now, db_index=True)
    tipo = models.CharField("qué pasó", max_length=20, choices=Tipo.choices)
    # Lo que se escribió en «Usuario» (también si ese usuario no existe)
    nombre_usuario = models.CharField("usuario", max_length=150, db_index=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accesos",
    )
    ip = models.GenericIPAddressField("dirección IP", null=True, blank=True)
    # Quién lo hizo, cuando no fue la misma persona (restablecer la contraseña, desbloquear)
    hecho_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-momento", "-pk"]
        verbose_name = "acceso"
        verbose_name_plural = "bitácora de accesos"

    def __str__(self):
        return f"{self.momento:%d/%m/%Y %H:%M} · {self.nombre_usuario} · {self.get_tipo_display()}"
