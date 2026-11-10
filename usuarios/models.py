from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


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
