"""Qué puede hacer cada rol de la clínica.

Este archivo es el único lugar donde se decide: para darle o quitarle algo a un
rol se cambia PERMISOS_POR_ROL y nada más. No hay que correr comandos ni tocar
la base de datos, porque el sistema lo consulta cada vez que alguien abre una
pantalla (ver usuarios/backends.py).

Los permisos son los normales de Django, con la forma «app.accion_modelo»:
    view = ver · add = crear · change = editar
Son los mismos que ya piden las vistas (por ejemplo, registrar un paciente pide
«pacientes.add_paciente»).

Nadie borra desde el sistema: los pacientes se dan de baja, las citas se
cancelan y los usuarios se desactivan. Solo un superusuario puede borrar.
"""
from .models import Usuario

Rol = Usuario.Rol

VER, CREAR, EDITAR = "view", "add", "change"


def permisos(app, modelo, *acciones):
    """permisos("citas", "cita", VER, CREAR) -> {"citas.view_cita", "citas.add_cita"}"""
    return frozenset(f"{app}.{accion}_{modelo}" for accion in acciones)


# Recepción: registra pacientes, busca expedientes y maneja la agenda y el inventario.
# Entrega lo que el médico recetó (ve la receta, pero no el diagnóstico).
_RECEPCION = (
    permisos("pacientes", "paciente", VER, CREAR, EDITAR)
    | permisos("citas", "cita", VER, CREAR, EDITAR)
    | permisos("inventario", "producto", VER, CREAR, EDITAR)
    | permisos("inventario", "movimiento", VER, CREAR)  # entradas, salidas e historial
    | permisos("consultas", "medicamentorecetado", VER)
    | {"consultas.entregar_medicamentorecetado"}
)

# Médico: atiende (consulta, diagnóstico y receta), actualiza el expediente y lleva su agenda.
# No registra pacientes nuevos y el inventario solo lo consulta (lo recetado lo entrega Recepción).
_MEDICO = (
    permisos("pacientes", "paciente", VER, EDITAR)
    | permisos("citas", "cita", VER, CREAR, EDITAR)
    | permisos("inventario", "producto", VER)
    | permisos("consultas", "consulta", VER, CREAR, EDITAR)
    | permisos("consultas", "medicamentorecetado", VER, CREAR, EDITAR)
)

# Administrador: todo lo de Recepción, más los usuarios, la bitácora de accesos y el panel de administración.
# Puede leer las consultas, pero no las escribe (eso es del médico).
_ADMINISTRADOR = (
    _RECEPCION
    | permisos("consultas", "consulta", VER)
    | permisos("usuarios", "usuario", VER, CREAR, EDITAR)
    | permisos("usuarios", "acceso", VER)  # bitácora de accesos
    # Para revisar todo desde el panel de administración (/admin/):
    | permisos("pacientes", "historialclinico", VER, EDITAR)
    | permisos("pacientes", "departamento", VER)
    | permisos("pacientes", "municipio", VER)
    | permisos("pacientes", "distrito", VER)
    | permisos("citas", "mensajesms", VER)
    | permisos("inventario", "categoria", VER, CREAR, EDITAR)
    | permisos("inventario", "lote", VER, EDITAR)
)

PERMISOS_POR_ROL = {
    Rol.ADMINISTRADOR: _ADMINISTRADOR,
    Rol.MEDICO: _MEDICO,
    Rol.RECEPCION: _RECEPCION,
}

DESCRIPCIONES = {
    Rol.ADMINISTRADOR: "Dirige la clínica: crea usuarios, asigna roles y revisa todo.",
    Rol.MEDICO: "Atiende: registra la consulta, el diagnóstico y la receta, y lleva su agenda.",
    Rol.RECEPCION: "Recibe al paciente: lo registra, maneja la agenda y el inventario y entrega lo recetado.",
}

# Lo mismo que PERMISOS_POR_ROL, dicho en palabras, para la pantalla «Usuarios y roles»
# y para docs/usuarios.md. Cada fila se marca según el permiso que la representa.
CAPACIDADES = [
    ("Pacientes", [
        ("Ver expedientes e historial clínico", "pacientes.view_paciente"),
        ("Registrar pacientes nuevos", "pacientes.add_paciente"),
        ("Actualizar el expediente y dar de baja", "pacientes.change_paciente"),
    ]),
    ("Citas", [
        ("Ver la agenda", "citas.view_cita"),
        ("Agendar citas", "citas.add_cita"),
        ("Confirmar, atender o cancelar citas y enviar recordatorios", "citas.change_cita"),
    ]),
    ("Consultas y recetas", [
        ("Atender: registrar la consulta, el diagnóstico y la receta", "consultas.add_consulta"),
        ("Ver las consultas y los diagnósticos", "consultas.view_consulta"),
        ("Ver e imprimir las recetas", "consultas.view_medicamentorecetado"),
        ("Entregar lo recetado (se descuenta del inventario)", "consultas.entregar_medicamentorecetado"),
    ]),
    ("Inventario", [
        ("Consultar existencias y el panel por categorías", "inventario.view_producto"),
        ("Crear y editar productos", "inventario.change_producto"),
        ("Registrar entradas y salidas", "inventario.add_movimiento"),
        ("Ver el historial de movimientos", "inventario.view_movimiento"),
    ]),
    ("Reportes", [
        ("Reporte del mes: pacientes y citas", "citas.view_cita"),
        ("Reporte del mes: compras, ventas y ganancia", "inventario.view_movimiento"),
    ]),
    ("Administración", [
        ("Ver los usuarios y sus roles", "usuarios.view_usuario"),
        ("Crear usuarios, asignar roles y entrar al panel de administración", "usuarios.change_usuario"),
        ("Restablecer contraseñas olvidadas y desbloquear usuarios", "usuarios.change_usuario"),
        ("Ver la bitácora de accesos: quién entró y los intentos fallidos", "usuarios.view_acceso"),
    ]),
]


def permisos_del_rol(rol):
    """Permisos de un rol; conjunto vacío si el rol no existe."""
    return PERMISOS_POR_ROL.get(rol, frozenset())


def matriz():
    """La tabla «qué puede hacer cada rol», lista para mostrarse.

    [{"modulo": "Pacientes", "filas": [{"texto": "...", "celdas": [True, True, False]}]}]
    Las celdas van en el orden de Rol.choices.
    """
    return [
        {
            "modulo": modulo,
            "filas": [
                {"texto": texto, "celdas": [permiso in permisos_del_rol(rol) for rol in Rol.values]}
                for texto, permiso in filas
            ],
        }
        for modulo, filas in CAPACIDADES
    ]
