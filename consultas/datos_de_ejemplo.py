"""Datos de ejemplo para probar o presentar el sistema (comando cargar_datos_de_ejemplo).

Arma una clínica con movimiento: usuarios de los tres roles, pacientes con su historial,
inventario (con algo por vencer, un lote vencido y productos bajo el mínimo), citas de las
semanas pasadas, de hoy y de los próximos días, consultas con receta, entregas y ventas.

Todo es inventado. Las fechas se calculan a partir de hoy, así que conviene cargarlos el
mismo día en que se van a usar (python manage.py preparar_presentacion).

Se usan las mismas funciones que usan las pantallas (inventario.services, consultas.entregas),
así que el stock y el historial de movimientos quedan como si se hubiera trabajado de verdad.
"""
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from citas.models import Cita, MensajeSMS
from citas.recordatorios import texto_recordatorio
from inventario import services
from inventario.models import Categoria, Lote, Movimiento, Producto
from pacientes.models import Distrito, HistorialClinico, Paciente

from . import entregas
from .models import Consulta, MedicamentoRecetado

VENTA = Movimiento.Concepto.VENTA
USO = Movimiento.Concepto.USO_INTERNO

# ---------------------------------------------------------------------------
# Usuarios: (usuario, nombre, apellido, rol). Todos con la misma contraseña.
# ---------------------------------------------------------------------------
USUARIOS = [
    ("administrador", "Carmen", "Rivas", "ADMIN"),
    ("dra.lopez", "Ana", "López", "MEDICO"),
    ("dr.martinez", "Roberto", "Martínez", "MEDICO"),
    ("recepcion", "Sofía", "Hernández", "RECEPCION"),
]
NOMBRES_DE_USUARIO = [usuario for usuario, *_ in USUARIOS]

# ---------------------------------------------------------------------------
# Pacientes. «registrado_hace» = hace cuántos días se registró (antes de su primera cita).
# Los adultos llevan un DUI inventado (válido); los menores, su responsable.
# ---------------------------------------------------------------------------
PACIENTES = [
    dict(clave="maria", nombres="María Elena", primer_apellido="Pérez", segundo_apellido="Gómez",
         sexo="F", nacimiento=(1979, 3, 14), estado_civil="CASADO", ocupacion="Maestra",
         afiliacion="ISBM", distrito="San Salvador", direccion="Colonia Escalón, calle El Mirador, casa 12",
         registrado_hace=62,
         historial=dict(tipo_sangre="O+", alergias="Penicilina",
                        enfermedades_cronicas="Hipertensión arterial",
                        medicamentos_actuales="Losartán 50 mg, una tableta al día")),
    dict(clave="jose", nombres="José Antonio", primer_apellido="Ramírez", segundo_apellido="Castillo",
         sexo="M", nacimiento=(1958, 7, 2), estado_civil="VIUDO", ocupacion="Agricultor jubilado",
         afiliacion="NINGUNA", distrito="Apopa", area="R", direccion="Cantón Guadalupe, caserío Los Pinos, casa 4",
         registrado_hace=60,
         historial=dict(tipo_sangre="A+", enfermedades_cronicas="Diabetes tipo 2\nHipertensión arterial",
                        medicamentos_actuales="Metformina 850 mg cada 12 horas\nLosartán 50 mg al día",
                        antecedentes_familiares="Madre con diabetes.")),
    dict(clave="lucia", nombres="Lucía Fernanda", primer_apellido="Martínez", segundo_apellido="Flores",
         sexo="F", nacimiento=(1995, 11, 20), estado_civil="SOLTERO", ocupacion="Contadora",
         afiliacion="ISSS", distrito="Santa Tecla", direccion="Residencial Las Palmas, pasaje 3, casa 27",
         registrado_hace=55, historial=dict(tipo_sangre="B+")),
    dict(clave="carlos", nombres="Carlos Ernesto", primer_apellido="Hernández", segundo_apellido="Rivas",
         sexo="M", nacimiento=(1988, 1, 9), estado_civil="ACOMPANADO", ocupacion="Mecánico",
         distrito="Soyapango", direccion="Colonia Los Ángeles, calle principal, casa 8",
         registrado_hace=50,
         historial=dict(tipo_sangre="O-", alergias="Ibuprofeno (le salen ronchas en la piel)")),
    dict(clave="ana", nombres="Ana Gabriela", primer_apellido="Rodríguez", segundo_apellido="Lemus",
         apellido_casada="Mejía", sexo="F", nacimiento=(1970, 5, 30), estado_civil="CASADO",
         ocupacion="Comerciante", afiliacion="PRIVADO", distrito="San Salvador",
         direccion="Barrio San Miguelito, 5.ª avenida norte, casa 1520", registrado_hace=48,
         historial=dict(tipo_sangre="A-", enfermedades_cronicas="Hipotiroidismo",
                        medicamentos_actuales="Levotiroxina 50 mcg en ayunas",
                        antecedentes_personales="Cesárea en 1998.")),
    dict(clave="mateo", nombres="Mateo Alejandro", primer_apellido="Flores", segundo_apellido="Peña",
         sexo="M", nacimiento=(2019, 4, 11), tipo_documento="PARTIDA", numero_documento="PN-2019-004512",
         distrito="Mejicanos", direccion="Colonia Zacamil, edificio 14, apartamento 3",
         responsable=("Karla Beatriz Peña", "MADRE"), registrado_hace=45,
         historial=dict(tipo_sangre="O+", enfermedades_cronicas="Asma leve",
                        alergias="Polvo y ácaros")),
    dict(clave="rosa", nombres="Rosa Amelia", primer_apellido="Guzmán", segundo_apellido="Rivera",
         apellido_casada="Ortiz", sexo="F", nacimiento=(1948, 12, 1), estado_civil="VIUDO",
         ocupacion="Ama de casa", distrito="Ciudad Delgado",
         direccion="Barrio El Centro, 2.ª calle oriente, casa 33", registrado_hace=44,
         historial=dict(tipo_sangre="B-", alergias="Sulfas",
                        enfermedades_cronicas="Osteoartritis de rodillas\nHipertensión arterial",
                        antecedentes_personales="Operada de la vesícula en 2010.")),
    dict(clave="francisco", nombres="Francisco Javier", primer_apellido="Ortiz", segundo_apellido="Lemus",
         sexo="M", nacimiento=(1965, 9, 8), estado_civil="CASADO", ocupacion="Carpintero",
         distrito="Ilopango", direccion="Colonia Santa Lucía, pasaje 7, casa 15", registrado_hace=40,
         historial=dict(tipo_sangre="O+", enfermedades_cronicas="Gastritis crónica")),
    dict(clave="daniela", nombres="Daniela Beatriz", primer_apellido="Cruz", segundo_apellido="Henríquez",
         sexo="F", nacimiento=(2001, 2, 25), estado_civil="SOLTERO", ocupacion="Estudiante universitaria",
         distrito="San Salvador", direccion="Colonia Miramonte, calle Sisimiles, casa 45",
         registrado_hace=38, historial=dict(tipo_sangre="AB+")),
    dict(clave="jorge", nombres="Jorge Luis", primer_apellido="Alvarado", segundo_apellido="Menjívar",
         sexo="M", nacimiento=(1990, 6, 17), estado_civil="CASADO", ocupacion="Motorista",
         afiliacion="ISSS", distrito="Soyapango", direccion="Urbanización Montes de San Bartolo, casa 210",
         registrado_hace=21, historial=dict(tipo_sangre="A+")),
    dict(clave="valeria", nombres="Valeria Sofía", primer_apellido="Mejía", segundo_apellido="Ramos",
         sexo="F", nacimiento=(2023, 8, 5), tipo_documento="NUI", numero_documento="100458731",
         distrito="Santa Tecla", direccion="Colonia Quezaltepec, calle 4, casa 18",
         responsable=("Jorge Alberto Mejía", "PADRE"), registrado_hace=18,
         historial=dict(tipo_sangre="O+")),
    dict(clave="gabriela", nombres="Gabriela Alejandra", primer_apellido="Portillo", segundo_apellido="Sánchez",
         sexo="F", nacimiento=(1984, 10, 13), estado_civil="DIVORCIADO", ocupacion="Enfermera",
         distrito="Mejicanos", direccion="Colonia Jardín, avenida Los Laureles, casa 9",
         registrado_hace=17, historial=dict(tipo_sangre="B+", alergias="Aspirina")),
    dict(clave="samuel", nombres="Samuel Isaac", primer_apellido="Hernández", segundo_apellido="López",
         sexo="M", nacimiento=(2011, 3, 3), tipo_documento="MINORIDAD", numero_documento="MIN-0457812",
         distrito="Apopa", direccion="Colonia Valle Verde, pasaje 2, casa 60",
         responsable=("Mario Ernesto Hernández", "PADRE"), registrado_hace=14,
         historial=dict(tipo_sangre="A+")),
    dict(clave="patricia", nombres="Patricia Carolina", primer_apellido="Molina", segundo_apellido="Avelar",
         sexo="F", nacimiento=(1999, 7, 21), estado_civil="SOLTERO", ocupacion="Diseñadora gráfica",
         distrito="Santa Tecla", direccion="Residencial Pinares, senda 5, casa 11",
         registrado_hace=15, historial=dict(tipo_sangre="O+")),
]

# ---------------------------------------------------------------------------
# Inventario: (código, nombre, tipo, categoría, presentación, unidad, mínimo, precio, lotes)
# Lote: (número, vence en cuántos días (None = no vence), cantidad, costo por unidad)
# ---------------------------------------------------------------------------
PRODUCTOS = [
    ("MED-001", "Acetaminofén", "MED", "Analgésicos y antipiréticos", "tableta 500 mg", "tableta", 100, "0.10",
     [("AC-2611", 300, 500, "0.04")]),
    ("MED-002", "Acetaminofén jarabe", "MED", "Analgésicos y antipiréticos", "jarabe 120 ml", "frasco", 10, "2.50",
     [("AJ-255", 20, 8, "1.20")]),  # por vencer y bajo el mínimo
    ("MED-003", "Ibuprofeno", "MED", "Antiinflamatorios", "tableta 400 mg", "tableta", 100, "0.15",
     [("IB-118", 400, 300, "0.06")]),
    ("MED-004", "Amoxicilina", "MED", "Antibióticos", "cápsula 500 mg", "cápsula", 60, "0.35",
     [("AM-092", 250, 200, "0.15")]),
    ("MED-005", "Amoxicilina suspensión", "MED", "Antibióticos", "250 mg/5 ml, frasco de 100 ml", "frasco", 5, "4.00",
     [("AS-031", 15, 6, "2.00")]),  # por vencer
    ("MED-006", "Loratadina", "MED", "Gripe y resfriado", "tableta 10 mg", "tableta", 50, "0.20",
     [("LR-774", 500, 120, "0.07")]),
    ("MED-007", "Salbutamol inhalador", "MED", "Vías respiratorias", "inhalador 100 mcg", "inhalador", 5, "6.50",
     [("SB-220", 365, 3, "3.75")]),  # bajo el mínimo
    ("MED-008", "Omeprazol", "MED", "Gastrointestinales", "cápsula 20 mg", "cápsula", 60, "0.25",
     [("OM-551", 420, 200, "0.08")]),
    ("MED-009", "Sales de rehidratación oral", "MED", "Gastrointestinales", "sobre para 1 litro", "sobre", 30, "0.60",
     [("SR-310", -10, 15, "0.25"), ("SR-402", 200, 60, "0.25")]),  # un lote vencido
    ("MED-010", "Losartán", "MED", "Cardiovasculares", "tableta 50 mg", "tableta", 60, "0.30",
     [("LS-640", 540, 300, "0.10")]),
    ("MED-011", "Metformina", "MED", "Diabetes", "tableta 850 mg", "tableta", 60, "0.18",
     [("MT-117", 480, 300, "0.06")]),
    ("MED-012", "Complejo B", "MED", "Vitaminas y suplementos", "tableta", "tableta", 30, "0.12",
     [("CB-881", 330, 90, "0.05")]),
    ("MED-013", "Hidrocortisona crema", "MED", "Dermatológicos", "crema 1 %, tubo de 15 g", "tubo", 5, "3.25",
     [("HC-045", 270, 12, "1.60")]),
    ("MED-014", "Diclofenaco", "MED", "Antiinflamatorios", "tableta 50 mg", "tableta", 50, "0.15",
     [("DC-303", 600, 150, "0.05")]),
    ("INS-001", "Gasa estéril", "INS", "Material de curación", "sobre de 10 unidades", "sobre", 20, "0.75",
     [("GS-900", None, 50, "0.30")]),
    ("INS-002", "Jeringa 5 ml", "INS", "Material de curación", "jeringa descartable con aguja", "unidad", 50, "0.25",
     [("JR-500", 900, 40, "0.09")]),  # bajo el mínimo
]
DIAS_DESDE_LA_COMPRA = 45
# Compras más recientes (para que el reporte del mes también tenga compras):
# (hace cuántos días, código, lote, vence en cuántos días, cantidad, costo)
RESURTIDO = [
    (12, "MED-006", "LR-801", 520, 60, "0.07"),
    (8, "MED-001", "AC-2711", 330, 200, "0.04"),
    (5, "MED-004", "AM-105", 280, 100, "0.15"),
]

# ---------------------------------------------------------------------------
# Casos de consulta. Receta: (código o None, nombre si es de afuera, dosis, frecuencia,
# duración, cantidad, indicaciones)
# ---------------------------------------------------------------------------
CASOS = {
    "faringitis": dict(
        motivo="Dolor de garganta y fiebre",
        sintomas="Fiebre de 38.5 °C desde hace 2 días y dolor al tragar. Amígdalas inflamadas con placas.",
        diagnostico="Faringoamigdalitis bacteriana",
        indicaciones="Tomar bastantes líquidos y reposo por 2 días. Volver si la fiebre sigue después de 3 días.",
        receta=[("MED-004", "", "1 cápsula", "cada 8 horas", "por 7 días", 21, "después de comer"),
                ("MED-001", "", "1 tableta", "cada 6 horas si hay fiebre", "por 3 días", 10, "")]),
    "resfriado": dict(
        motivo="Gripe y congestión nasal",
        sintomas="Estornudos, nariz tapada y malestar general desde hace 3 días. Sin fiebre.",
        diagnostico="Resfriado común",
        indicaciones="Reposo, líquidos tibios y lavados nasales con suero fisiológico.",
        receta=[("MED-006", "", "1 tableta", "cada 24 horas", "por 5 días", 5, ""),
                ("MED-001", "", "1 tableta", "cada 8 horas si hay dolor", "por 3 días", 10, "")]),
    "presion": dict(
        motivo="Control de presión arterial",
        sintomas="Presión 135/85. Sin dolor de cabeza ni mareos.",
        diagnostico="Hipertensión arterial controlada",
        indicaciones="Seguir con la dieta baja en sal y caminar 30 minutos al día. Control en un mes.",
        receta=[("MED-010", "", "1 tableta", "cada 24 horas", "por 30 días", 30, "en la mañana")]),
    "diabetes": dict(
        motivo="Control de azúcar",
        sintomas="Glucosa en ayunas 128 mg/dl. Sin molestias.",
        diagnostico="Diabetes mellitus tipo 2 en control",
        indicaciones="Evitar azúcar y harinas. Traer examen de hemoglobina glicosilada en el próximo control.",
        receta=[("MED-011", "", "1 tableta", "cada 12 horas", "por 30 días", 60, "con las comidas")]),
    "gastritis": dict(
        motivo="Ardor en el estómago",
        sintomas="Ardor en la boca del estómago después de comer, desde hace una semana.",
        diagnostico="Gastritis aguda",
        indicaciones="Comer a sus horas y evitar café, picante y comidas grasosas.",
        receta=[("MED-008", "", "1 cápsula", "cada 24 horas", "por 14 días", 14, "en ayunas")]),
    "lumbalgia": dict(
        motivo="Dolor de espalda baja",
        sintomas="Dolor en la cintura desde que cargó peso hace 2 días. Sin dolor en las piernas.",
        diagnostico="Lumbalgia mecánica",
        indicaciones="Compresas tibias y no cargar peso por una semana.",
        receta=[("MED-014", "", "1 tableta", "cada 12 horas", "por 5 días", 10, "después de comer")]),
    "diarrea": dict(
        motivo="Diarrea",
        sintomas="Cuatro evacuaciones líquidas desde ayer. Sin sangre. Bien hidratado.",
        diagnostico="Enfermedad diarreica aguda sin deshidratación",
        indicaciones="Dieta blanda y tomar el suero en pequeños tragos. Volver si hay sangre o fiebre.",
        receta=[("MED-009", "", "1 sobre en 1 litro de agua", "después de cada evacuación", "por 2 días", 4, "")]),
    "dermatitis": dict(
        motivo="Ronchas con picazón en los brazos",
        sintomas="Placas rojas con picazón en ambos antebrazos después de usar un detergente nuevo.",
        diagnostico="Dermatitis de contacto",
        indicaciones="Dejar de usar ese detergente y no rascarse.",
        receta=[("MED-013", "", "una capa delgada", "cada 12 horas", "por 7 días", 1, "sobre la piel afectada")]),
    "asma": dict(
        motivo="Tos y silbido en el pecho",
        sintomas="Tos de noche y silbido al respirar desde hace 2 días. Saturación 96 %.",
        diagnostico="Crisis asmática leve",
        indicaciones="Usar el inhalador con espaciador. Volver de inmediato si le cuesta respirar.",
        receta=[("MED-007", "", "2 inhalaciones", "cada 6 horas", "por 5 días", 1, "con espaciador")]),
    "nino_sano": dict(
        motivo="Control de niña sana",
        sintomas="Peso y talla adecuados para su edad. Vacunas al día.",
        diagnostico="Niña sana, crecimiento y desarrollo adecuados",
        indicaciones="Seguir con la alimentación variada. Próximo control en 3 meses.",
        receta=[(None, "Multivitamínico infantil en gotas", "1 ml", "una vez al día", "por 30 días", 1, "")]),
    "tiroides": dict(
        motivo="Control de tiroides",
        sintomas="Se siente bien. TSH del mes pasado en rango normal.",
        diagnostico="Hipotiroidismo en tratamiento",
        indicaciones="Seguir con la misma dosis. Examen de TSH en 6 meses.",
        receta=[(None, "Levotiroxina 50 mcg", "1 tableta", "cada 24 horas", "por 30 días", 30, "en ayunas")]),
    "cansancio": dict(
        motivo="Cansancio",
        sintomas="Se cansa con facilidad desde hace un mes. Palidez leve.",
        diagnostico="Anemia leve por falta de hierro (por confirmar con hemograma)",
        indicaciones="Hacerse un hemograma. Comer frijoles, hígado y vegetales verdes.",
        receta=[("MED-012", "", "1 tableta", "cada 24 horas", "por 30 días", 30, ""),
                (None, "Sulfato ferroso 300 mg", "1 tableta", "cada 24 horas", "por 30 días", 30, "con jugo de naranja")]),
    "artritis": dict(
        motivo="Dolor de rodillas",
        sintomas="Dolor en ambas rodillas al caminar, peor en las mañanas.",
        diagnostico="Osteoartritis de rodillas",
        indicaciones="Caminar en terreno plano y bajar de peso poco a poco.",
        receta=[("MED-001", "", "1 tableta", "cada 8 horas si hay dolor", "por 10 días", 30, "")]),
}

# ---------------------------------------------------------------------------
# Agenda
# ---------------------------------------------------------------------------
# Citas pasadas: (hace cuántos días, hora, médico, paciente, caso o estado, entrega)
# entrega: VENTA, USO (sin costo) o None (todavía por entregar)
PASADAS = [
    (34, "08:00", "dra.lopez", "maria", "presion", VENTA),
    (33, "09:30", "dr.martinez", "jose", "diabetes", VENTA),
    (31, "10:00", "dra.lopez", "lucia", "faringitis", VENTA),
    (30, "14:00", "dr.martinez", "rosa", "artritis", VENTA),
    (28, "08:30", "dra.lopez", "mateo", "asma", VENTA),
    (27, "11:00", "dr.martinez", "carlos", "resfriado", VENTA),
    (24, "09:00", "dra.lopez", "ana", "tiroides", VENTA),
    (23, "15:00", "dr.martinez", "francisco", "gastritis", VENTA),
    (21, "10:30", "dra.lopez", "daniela", "resfriado", VENTA),
    (20, "08:00", "dr.martinez", "jorge", Cita.Estado.NO_ASISTIO, None),
    (17, "09:00", "dra.lopez", "valeria", "nino_sano", VENTA),
    (16, "14:30", "dr.martinez", "gabriela", "dermatitis", VENTA),
    (14, "10:00", "dra.lopez", "patricia", "cansancio", VENTA),
    (13, "08:30", "dr.martinez", "samuel", "faringitis", VENTA),
    (10, "11:30", "dra.lopez", "lucia", Cita.Estado.CANCELADA, None),
    (9, "09:00", "dr.martinez", "jose", "presion", VENTA),
    (7, "15:30", "dra.lopez", "carlos", "gastritis", VENTA),
    (6, "10:00", "dr.martinez", "rosa", Cita.Estado.NO_ASISTIO, None),
    (5, "08:00", "dra.lopez", "jorge", "diarrea", USO),
    (3, "14:00", "dr.martinez", "daniela", Cita.Estado.CANCELADA, None),
    (2, "09:30", "dra.lopez", "francisco", "lumbalgia", VENTA),
    (1, "10:00", "dr.martinez", "maria", "resfriado", None),   # Recepción todavía no lo entrega
    (1, "15:00", "dra.lopez", "patricia", "gastritis", None),  # Recepción todavía no lo entrega
]
# Consultas sin cita (el paciente llegó sin avisar): (hace cuántos días, hora, médico, paciente, caso)
SIN_CITA = [
    (4, "16:30", "dra.lopez", "samuel", "resfriado"),
]
# Citas de hoy: las que ya pasaron quedan atendidas (con la receta por entregar)
HOY = [
    ("08:00", "dra.lopez", "maria", "presion"),
    ("08:30", "dr.martinez", "jose", "diabetes"),
    ("09:00", "dra.lopez", "mateo", "asma"),
    ("10:00", "dr.martinez", "carlos", "resfriado"),
    ("10:30", "dra.lopez", "lucia", "cansancio"),
    ("11:00", "dr.martinez", "rosa", "artritis"),
    ("14:00", "dra.lopez", "daniela", "dermatitis"),
    ("14:30", "dr.martinez", "jorge", "lumbalgia"),
    ("15:30", "dra.lopez", "patricia", "cansancio"),
    ("16:00", "dr.martinez", "francisco", "gastritis"),
]
# Próximas citas: (dentro de cuántos días, hora, médico, paciente, motivo)
PROXIMAS = [
    (1, "08:30", "dr.martinez", "gabriela", "Control de la piel"),
    (1, "09:00", "dra.lopez", "ana", "Control de tiroides"),
    (1, "10:00", "dra.lopez", "samuel", "Revisión de garganta"),
    (1, "11:00", "dr.martinez", "valeria", "Vacunas y control de niña sana"),
    (2, "09:00", "dra.lopez", "jose", "Control de azúcar"),
    (2, "14:00", "dr.martinez", "lucia", "Resultados de exámenes"),
    (3, "08:00", "dr.martinez", "maria", "Control de presión arterial"),
    (3, "10:30", "dra.lopez", "daniela", "Dolor de cabeza frecuente"),
    (5, "09:30", "dra.lopez", "carlos", "Revisión de la gastritis"),
    (5, "15:00", "dr.martinez", "patricia", "Chequeo general"),
    (7, "10:00", "dra.lopez", "rosa", "Control de las rodillas"),
]
# Ventas de mostrador (sin receta): (hace cuántos días, código, cantidad)
VENTAS_DE_MOSTRADOR = [
    (40, "MED-001", 20), (26, "MED-001", 20), (19, "MED-006", 10), (11, "MED-003", 24),
    (8, "MED-012", 10), (4, "MED-001", 12), (2, "MED-008", 10), (1, "MED-003", 12),
]


def _momento(dia, hora):
    """Fecha (date) + '08:30' -> datetime con la zona horaria de la clínica."""
    horas, minutos = (int(parte) for parte in hora.split(":"))
    return timezone.make_aware(datetime.combine(dia, time(horas, minutos)))


def _dui(rng):
    """DUI inventado con dígito verificador correcto (ver pacientes/validators.py)."""
    cuerpo = f"0{rng.randrange(1_000_000, 10_000_000)}"
    suma = sum(int(digito) * (9 - posicion) for posicion, digito in enumerate(cuerpo))
    return f"{cuerpo}-{(10 - suma % 10) % 10}"


def _telefono_fijo(rng):
    """Teléfono fijo inventado (empieza con 2: no recibe SMS)."""
    return f"22{rng.randrange(100000, 1000000)}"


def _poner_fecha(movimientos, momento):
    Movimiento.objects.filter(pk__in=[m.pk for m in movimientos]).update(fecha=momento)


class _Carga:
    def __init__(self, clave, telefono, rng):
        self.clave = clave
        self.telefono = telefono
        self.rng = rng
        self.ahora = timezone.now()
        self.hoy = timezone.localdate()
        self.usuarios = {}
        self.pacientes = {}
        self.productos = {}

    # --- Usuarios ---------------------------------------------------------
    def usuarios_(self):
        Usuario = get_user_model()
        for usuario, nombre, apellido, rol in USUARIOS:
            self.usuarios[usuario] = Usuario.objects.create_user(
                usuario, password=self.clave, first_name=nombre, last_name=apellido, rol=rol
            )
        self.recepcion = self.usuarios["recepcion"]

    # --- Pacientes --------------------------------------------------------
    def pacientes_(self):
        distrito_por_defecto = Distrito.objects.order_by("pk").first()
        for datos in PACIENTES:
            datos = dict(datos)
            clave = datos.pop("clave")
            historial = datos.pop("historial", {})
            registrado_hace = datos.pop("registrado_hace")
            responsable = datos.pop("responsable", None)
            anio, mes, dia = datos.pop("nacimiento")
            distrito = Distrito.objects.filter(nombre=datos.pop("distrito")).first() or distrito_por_defecto
            telefono = self.telefono or _telefono_fijo(self.rng)
            paciente = Paciente(
                fecha_nacimiento=date(anio, mes, dia),
                distrito=distrito,
                area=datos.pop("area", Paciente.Area.URBANA),
                tipo_documento=datos.pop("tipo_documento", Paciente.TipoDocumento.DUI),
                telefono=telefono,
                consentimiento_datos=True,
                registrado_por=self.recepcion,
                **datos,
            )
            if paciente.tipo_documento == Paciente.TipoDocumento.DUI:
                paciente.numero_documento = _dui(self.rng)
            if responsable:
                nombre, parentesco = responsable
                paciente.responsable_nombre = nombre
                paciente.responsable_parentesco = parentesco
                paciente.responsable_dui = _dui(self.rng)
                paciente.responsable_telefono = telefono
                paciente.datos_proporcionados_por = f"{nombre} ({parentesco.lower()})"
            paciente.full_clean()
            paciente.save()
            expediente = paciente.historial  # se crea solo al guardar al paciente
            for campo, valor in historial.items():
                setattr(expediente, campo, valor)
            expediente.save()
            registrado = self.ahora - timedelta(days=registrado_hace, hours=self.rng.randrange(1, 6))
            Paciente.objects.filter(pk=paciente.pk).update(fecha_registro=registrado)
            HistorialClinico.objects.filter(pk=expediente.pk).update(fecha_apertura=registrado)
            self.pacientes[clave] = paciente

    # --- Inventario -------------------------------------------------------
    def inventario_(self):
        categorias = {c.nombre: c for c in Categoria.objects.all()}
        compra = self.ahora - timedelta(days=DIAS_DESDE_LA_COMPRA)
        for codigo, nombre, tipo, categoria, presentacion, unidad, minimo, precio, lotes in PRODUCTOS:
            producto = Producto.objects.create(
                codigo=codigo, nombre=nombre, tipo=tipo, categoria=categorias.get(categoria),
                presentacion=presentacion, unidad_medida=unidad, stock_minimo=minimo,
                precio_venta=Decimal(precio),
            )
            self.productos[codigo] = producto
            for numero, vence_en, cantidad, costo in lotes:
                vence = self.hoy + timedelta(days=vence_en) if vence_en is not None else None
                movimiento = services.registrar_entrada(
                    producto=producto, numero_lote=numero, cantidad=cantidad, fecha_vencimiento=vence,
                    usuario=self.recepcion, costo_unitario=Decimal(costo), motivo="Compra a la droguería",
                )
                _poner_fecha([movimiento], compra)
                Lote.objects.filter(pk=movimiento.lote_id).update(fecha_ingreso=compra)
        for dias, codigo, numero, vence_en, cantidad, costo in RESURTIDO:
            momento = self.ahora - timedelta(days=dias)
            movimiento = services.registrar_entrada(
                producto=self.productos[codigo], numero_lote=numero, cantidad=cantidad,
                fecha_vencimiento=self.hoy + timedelta(days=vence_en), usuario=self.recepcion,
                costo_unitario=Decimal(costo), motivo="Compra a la droguería",
            )
            _poner_fecha([movimiento], momento)
            Lote.objects.filter(pk=movimiento.lote_id).update(fecha_ingreso=momento)
        # Una donación y unas jeringas dañadas, para que se vean en el historial
        donacion = services.registrar_entrada(
            producto=self.productos["MED-012"], numero_lote="CB-DON1", cantidad=40,
            fecha_vencimiento=self.hoy + timedelta(days=300), usuario=self.recepcion,
            concepto=Movimiento.Concepto.DONACION, motivo="Donación de una farmacia del barrio",
        )
        _poner_fecha([donacion], self.ahora - timedelta(days=25))
        lote = Lote.objects.get(producto=self.productos["INS-002"], numero_lote="JR-500")
        merma = services.dar_de_baja(lote=lote, cantidad=2, usuario=self.recepcion, motivo="Empaque roto")
        _poner_fecha([merma], self.ahora - timedelta(days=8))

    # --- Consultas --------------------------------------------------------
    def atender(self, *, paciente, medico, fecha, caso, entrega, cita=None):
        datos = CASOS[caso]
        consulta = Consulta.objects.create(
            paciente=paciente, medico=medico, cita=cita, fecha=fecha, motivo=datos["motivo"],
            sintomas=datos["sintomas"], diagnostico=datos["diagnostico"], indicaciones=datos["indicaciones"],
        )
        for codigo, nombre, dosis, frecuencia, duracion, cantidad, indicaciones in datos["receta"]:
            medicamento = MedicamentoRecetado.objects.create(
                consulta=consulta, producto=self.productos.get(codigo) if codigo else None, nombre=nombre,
                dosis=dosis, frecuencia=frecuencia, duracion=duracion, cantidad=cantidad,
                indicaciones=indicaciones,
            )
            if entrega and medicamento.estado == MedicamentoRecetado.Estado.POR_ENTREGAR:
                entregas.entregar(medicamento, usuario=self.recepcion, concepto=entrega)
                momento = fecha + timedelta(minutes=35)
                MedicamentoRecetado.objects.filter(pk=medicamento.pk).update(entregado_en=momento)
                _poner_fecha(medicamento.movimientos.all(), momento)
        return consulta

    def cita(self, *, paciente, medico, fecha_hora, motivo, estado):
        return Cita.objects.create(
            paciente=paciente, medico=medico, fecha_hora=fecha_hora, motivo=motivo, estado=estado,
            creada_por=self.recepcion,
        )

    def recordatorio_simulado(self, cita):
        """El SMS que se habría mandado el día anterior a las 8:00 a. m."""
        enviado = _momento(timezone.localtime(cita.fecha_hora).date() - timedelta(days=1), "08:00")
        mensaje = MensajeSMS.objects.create(
            cita=cita, telefono=self.pacientes_por_pk[cita.paciente_id].telefono,
            texto=texto_recordatorio(cita), estado=MensajeSMS.Estado.SIMULADO, proveedor="simulado",
        )
        MensajeSMS.objects.filter(pk=mensaje.pk).update(creado=enviado)
        Cita.objects.filter(pk=cita.pk).update(recordatorio_enviado=enviado)

    def agenda_(self):
        self.pacientes_por_pk = {p.pk: p for p in self.pacientes.values()}
        medicos = self.usuarios

        for dias, hora, medico, paciente, caso, entrega in PASADAS:
            fecha_hora = _momento(self.hoy - timedelta(days=dias), hora)
            paciente = self.pacientes[paciente]
            if caso in CASOS:
                cita = self.cita(paciente=paciente, medico=medicos[medico], fecha_hora=fecha_hora,
                                 motivo=CASOS[caso]["motivo"], estado=Cita.Estado.ATENDIDA)
                self.atender(paciente=paciente, medico=medicos[medico], fecha=fecha_hora + timedelta(minutes=5),
                             caso=caso, entrega=entrega, cita=cita)
            else:
                cita = self.cita(paciente=paciente, medico=medicos[medico], fecha_hora=fecha_hora,
                                 motivo="Consulta general", estado=caso)
            if cita.estado != Cita.Estado.CANCELADA:
                self.recordatorio_simulado(cita)

        for dias, hora, medico, paciente, caso in SIN_CITA:
            self.atender(paciente=self.pacientes[paciente], medico=medicos[medico],
                         fecha=_momento(self.hoy - timedelta(days=dias), hora), caso=caso, entrega=VENTA)

        confirmadas = 0
        for hora, medico, paciente, caso in HOY:
            fecha_hora = _momento(self.hoy, hora)
            paciente = self.pacientes[paciente]
            if fecha_hora + timedelta(minutes=30) <= self.ahora:
                cita = self.cita(paciente=paciente, medico=medicos[medico], fecha_hora=fecha_hora,
                                 motivo=CASOS[caso]["motivo"], estado=Cita.Estado.ATENDIDA)
                self.atender(paciente=paciente, medico=medicos[medico], fecha=fecha_hora + timedelta(minutes=5),
                             caso=caso, entrega=None, cita=cita)
            else:
                estado = Cita.Estado.CONFIRMADA if confirmadas < 2 else Cita.Estado.PROGRAMADA
                confirmadas += 1
                cita = self.cita(paciente=paciente, medico=medicos[medico], fecha_hora=fecha_hora,
                                 motivo=CASOS[caso]["motivo"], estado=estado)
            self.recordatorio_simulado(cita)

        # Las próximas no tienen recordatorio todavía: se puede mandar con el botón de la cita
        for dias, hora, medico, paciente, motivo in PROXIMAS:
            self.cita(paciente=self.pacientes[paciente], medico=medicos[medico],
                      fecha_hora=_momento(self.hoy + timedelta(days=dias), hora), motivo=motivo,
                      estado=Cita.Estado.PROGRAMADA)

    def ventas_(self):
        for dias, codigo, cantidad in VENTAS_DE_MOSTRADOR:
            movimientos = services.registrar_salida(
                producto=self.productos[codigo], cantidad=cantidad, usuario=self.recepcion,
                concepto=VENTA, motivo="Venta de mostrador",
            )
            _poner_fecha(movimientos, _momento(self.hoy - timedelta(days=dias), "11:15"))


@transaction.atomic
def cargar(*, clave, telefono=""):
    """Carga todos los datos de ejemplo. telefono: el de todos los pacientes (para probar los SMS)."""
    carga = _Carga(clave, telefono, random.Random(2026))
    carga.usuarios_()
    carga.pacientes_()
    carga.inventario_()
    carga.ventas_()
    carga.agenda_()
    return {
        "usuarios": len(carga.usuarios),
        "pacientes": len(carga.pacientes),
        "productos": len(carga.productos),
        "citas_hoy": Cita.objects.filter(fecha_hora__date=carga.hoy).count(),
        "citas_proximas": Cita.objects.filter(fecha_hora__date__gt=carga.hoy).count(),
        "consultas": Consulta.objects.count(),
        "por_entregar": MedicamentoRecetado.objects.filter(
            estado=MedicamentoRecetado.Estado.POR_ENTREGAR
        ).count(),
    }
