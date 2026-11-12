from django.contrib import admin
from django.contrib.admin.utils import unquote
from django.contrib.auth.admin import UserAdmin

from . import accesos
from .models import Acceso, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Datos personales', {'fields': ('first_name', 'last_name', 'email')}),
        ('Rol en la clínica', {
            'fields': ('rol', 'is_active', 'debe_cambiar_clave'),
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

    def save_model(self, request, obj, form, change):
        # La contraseña que se pone al crear el usuario es temporal: al entrar creará la suya
        if not change and obj.has_usable_password():
            obj.debe_cambiar_clave = True
        super().save_model(request, obj, form, change)

    def user_change_password(self, request, id, form_url=""):
        respuesta = super().user_change_password(request, id, form_url)
        # Si el Administrador le puso una contraseña nueva a otra persona, también es temporal
        guardo = request.method == "POST" and respuesta.status_code == 302 and respuesta.url != request.get_full_path()
        if guardo:
            persona = Usuario.objects.filter(pk=unquote(id)).first()
            if persona and persona.pk != request.user.pk and persona.has_usable_password():
                persona.debe_cambiar_clave = True
                persona.save(update_fields=["debe_cambiar_clave"])
                accesos.registrar(Acceso.Tipo.CLAVE_RESTABLECIDA, usuario=persona, request=request,
                                  hecho_por=request.user)
        return respuesta

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


@admin.register(Acceso)
class AccesoAdmin(admin.ModelAdmin):
    """La bitácora se puede consultar, pero nadie la escribe ni la borra a mano."""

    list_display = ('momento', 'nombre_usuario', 'tipo', 'ip', 'hecho_por')
    list_filter = ('tipo',)
    search_fields = ('nombre_usuario',)
    date_hierarchy = 'momento'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
