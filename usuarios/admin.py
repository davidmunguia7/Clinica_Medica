from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Datos personales', {'fields': ('first_name', 'last_name', 'email')}),
        ('Rol en la clínica', {
            'fields': ('rol', 'is_active'),
            'description': (
                'El rol decide qué pantallas ve la persona y qué puede hacer. '
                'Para que alguien deje de entrar al sistema, desmarque «Activo» en lugar de borrarlo.'
            ),
        }),
        ('Permisos adicionales (casi nunca hacen falta)', {
            'classes': ('collapse',),
            'fields': ('is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'description': 'Se suman a los del rol. El acceso al panel de administración lo da el rol Administrador.',
        }),
        ('Fechas', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Datos personales', {'fields': ('first_name', 'last_name')}),
        ('Rol en la clínica', {'fields': ('rol',)}),
    )
    list_display = ('username', 'first_name', 'last_name', 'rol', 'is_active', 'last_login')
    list_filter = ('rol', 'is_active')
    # «is_staff» se calcula solo a partir del rol (Usuario.save)
    readonly_fields = ('is_staff', 'last_login', 'date_joined')

    def get_readonly_fields(self, request, obj=None):
        campos = super().get_readonly_fields(request, obj)
        if not request.user.is_superuser:
            # Un Administrador no puede volverse superusuario ni darse permisos sueltos
            campos = (*campos, 'is_superuser', 'groups', 'user_permissions')
        return campos

    def _es_superusuario_ajeno(self, request, obj):
        return obj is not None and obj.is_superuser and not request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        # Las cuentas de superusuario solo las cambia otro superusuario
        if self._es_superusuario_ajeno(request, obj):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if self._es_superusuario_ajeno(request, obj):
            return False
        return super().has_delete_permission(request, obj)
