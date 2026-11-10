"""Roles: deja listos a los usuarios que ya existían.

Hasta ahora el rol no cambiaba nada, así que:
- Los superusuarios (creados con «createsuperuser») quedaron con el rol por
  defecto, Recepción. Pasan a Administrador, que es lo que son.
- Al panel de administración entran el Administrador y los superusuarios;
  los demás roles, no.
"""
import usuarios.models
from django.db import migrations


def ajustar_usuarios_existentes(apps, schema_editor):
    Usuario = apps.get_model('usuarios', 'Usuario')
    Usuario.objects.filter(is_superuser=True, rol='RECEPCION').update(rol='ADMIN')
    Usuario.objects.filter(rol='ADMIN').update(is_staff=True)
    Usuario.objects.filter(is_superuser=False).exclude(rol='ADMIN').update(is_staff=False)


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelManagers(
            name='usuario',
            managers=[
                ('objects', usuarios.models.UsuarioManager()),
            ],
        ),
        migrations.RunPython(ajustar_usuarios_existentes, migrations.RunPython.noop),
    ]
