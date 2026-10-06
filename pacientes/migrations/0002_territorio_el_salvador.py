"""Carga la división territorial de El Salvador vigente desde el 1 de mayo de 2024.

Ley Especial para la Reestructuración Municipal: 14 departamentos,
44 municipios y 262 distritos (los antiguos municipios pasaron a ser distritos).
Fuente: listado de la ley publicado por Diario El Mundo y el anexo
"Municipios y distritos de El Salvador" de Wikipedia.
"""
from django.db import migrations

# (código ISO 3166-2, departamento, [(municipio, [distritos])])
TERRITORIO = [
    ("SV-AH", "Ahuachapán", [
        ("Ahuachapán Norte", ["Atiquizaya", "El Refugio", "San Lorenzo", "Turín"]),
        ("Ahuachapán Centro", ["Ahuachapán", "Apaneca", "Concepción de Ataco", "Tacuba"]),
        ("Ahuachapán Sur", ["Guaymango", "Jujutla", "San Francisco Menéndez", "San Pedro Puxtla"]),
    ]),
    ("SV-CA", "Cabañas", [
        ("Cabañas Este", ["Guacotecti", "San Isidro", "Sensuntepeque", "Victoria", "Dolores"]),
        ("Cabañas Oeste", ["Cinquera", "Ilobasco", "Jutiapa", "Tejutepeque"]),
    ]),
    ("SV-CH", "Chalatenango", [
        ("Chalatenango Norte", ["Citalá", "La Palma", "San Ignacio"]),
        ("Chalatenango Centro", [
            "Agua Caliente", "Dulce Nombre de María", "El Paraíso", "La Reina",
            "Nueva Concepción", "San Fernando", "San Francisco Morazán", "San Rafael",
            "Santa Rita", "Tejutla",
        ]),
        ("Chalatenango Sur", [
            "Arcatao", "Azacualpa", "San José Cancasque", "Chalatenango", "Comalapa",
            "Concepción Quezaltepeque", "El Carrizal", "La Laguna", "Las Vueltas",
            "San José Las Flores", "Nombre de Jesús", "Nueva Trinidad", "Ojos de Agua",
            "Potonico", "San Antonio de la Cruz", "San Antonio Los Ranchos",
            "San Francisco Lempa", "San Isidro Labrador", "San Luis del Carmen",
            "San Miguel de Mercedes",
        ]),
    ]),
    ("SV-CU", "Cuscatlán", [
        ("Cuscatlán Norte", [
            "Suchitoto", "San José Guayabal", "Oratorio de Concepción",
            "San Bartolomé Perulapía", "San Pedro Perulapán",
        ]),
        ("Cuscatlán Sur", [
            "Cojutepeque", "Candelaria", "El Carmen", "El Rosario", "Monte San Juan",
            "San Cristóbal", "San Rafael Cedros", "San Ramón", "Santa Cruz Analquito",
            "Santa Cruz Michapa", "Tenancingo",
        ]),
    ]),
    ("SV-LI", "La Libertad", [
        ("La Libertad Norte", ["Quezaltepeque", "San Matías", "San Pablo Tacachico"]),
        ("La Libertad Centro", ["San Juan Opico", "Ciudad Arce"]),
        ("La Libertad Oeste", ["Colón", "Jayaque", "Sacacoyo", "Tepecoyo", "Talnique"]),
        ("La Libertad Este", [
            "Antiguo Cuscatlán", "Huizúcar", "Nuevo Cuscatlán", "San José Villanueva", "Zaragoza",
        ]),
        ("La Libertad Costa", ["Chiltiupán", "Jicalapa", "La Libertad", "Tamanique", "Teotepeque"]),
        ("La Libertad Sur", ["Santa Tecla", "Comasagua"]),
    ]),
    ("SV-PA", "La Paz", [
        ("La Paz Oeste", [
            "Cuyultitán", "Olocuilta", "San Juan Talpa", "San Luis Talpa",
            "San Pedro Masahuat", "Tapalhuaca", "San Francisco Chinameca",
        ]),
        ("La Paz Centro", [
            "El Rosario", "Jerusalén", "Mercedes La Ceiba", "Paraíso de Osorio",
            "San Antonio Masahuat", "San Emigdio", "San Juan Tepezontes",
            "San Luis La Herradura", "San Miguel Tepezontes", "San Pedro Nonualco",
            "Santa María Ostuma", "Santiago Nonualco",
        ]),
        ("La Paz Este", ["San Juan Nonualco", "San Rafael Obrajuelo", "Zacatecoluca"]),
    ]),
    ("SV-UN", "La Unión", [
        ("La Unión Norte", [
            "Anamorós", "Bolívar", "Concepción de Oriente", "El Sauce", "Lislique",
            "Nueva Esparta", "Pasaquina", "Polorós", "San José", "Santa Rosa de Lima",
        ]),
        ("La Unión Sur", [
            "Conchagua", "El Carmen", "Intipucá", "La Unión", "Meanguera del Golfo",
            "San Alejo", "Yayantique", "Yucuaiquín",
        ]),
    ]),
    ("SV-MO", "Morazán", [
        ("Morazán Norte", [
            "Arambala", "Cacaopera", "Corinto", "El Rosario", "Joateca", "Jocoaitique",
            "Meanguera", "Perquín", "San Fernando", "San Isidro", "Torola",
        ]),
        ("Morazán Sur", [
            "Chilanga", "Delicias de Concepción", "El Divisadero", "Gualococti",
            "Guatajiagua", "Jocoro", "Lolotiquillo", "Osicala", "San Carlos",
            "San Francisco Gotera", "San Simón", "Sensembra", "Sociedad", "Yamabal",
            "Yoloaiquín",
        ]),
    ]),
    ("SV-SM", "San Miguel", [
        ("San Miguel Norte", [
            "Ciudad Barrios", "Sesori", "Nuevo Edén de San Juan", "San Gerardo",
            "San Luis de la Reina", "Carolina", "San Antonio del Mosco", "Chapeltique",
        ]),
        ("San Miguel Centro", [
            "San Miguel", "Comacarán", "Uluazapa", "Moncagua", "Quelepa", "Chirilagua",
        ]),
        ("San Miguel Oeste", [
            "Chinameca", "El Tránsito", "Lolotique", "Nueva Guadalupe", "San Jorge",
            "San Rafael Oriente",
        ]),
    ]),
    ("SV-SS", "San Salvador", [
        ("San Salvador Norte", ["Aguilares", "El Paisnal", "Guazapa"]),
        ("San Salvador Oeste", ["Apopa", "Nejapa"]),
        ("San Salvador Este", ["Ilopango", "San Martín", "Soyapango", "Tonacatepeque"]),
        ("San Salvador Centro", [
            "Ayutuxtepeque", "Mejicanos", "Cuscatancingo", "Ciudad Delgado", "San Salvador",
        ]),
        ("San Salvador Sur", [
            "San Marcos", "Santo Tomás", "Santiago Texacuangos", "Panchimalco", "Rosario de Mora",
        ]),
    ]),
    ("SV-SV", "San Vicente", [
        ("San Vicente Norte", [
            "Apastepeque", "Santa Clara", "San Ildefonso", "San Esteban Catarina",
            "San Sebastián", "San Lorenzo", "Santo Domingo",
        ]),
        ("San Vicente Sur", [
            "San Vicente", "Guadalupe", "San Cayetano Istepeque", "Tecoluca", "Tepetitán", "Verapaz",
        ]),
    ]),
    ("SV-SA", "Santa Ana", [
        ("Santa Ana Norte", ["Masahuat", "Metapán", "Santa Rosa Guachipilín", "Texistepeque"]),
        ("Santa Ana Centro", ["Santa Ana"]),
        ("Santa Ana Este", ["Coatepeque", "El Congo"]),
        ("Santa Ana Oeste", [
            "Candelaria de la Frontera", "Chalchuapa", "El Porvenir", "San Antonio Pajonal",
            "San Sebastián Salitrillo", "Santiago de la Frontera",
        ]),
    ]),
    ("SV-SO", "Sonsonate", [
        ("Sonsonate Norte", ["Juayúa", "Nahuizalco", "Salcoatitán", "Santa Catarina Masahuat"]),
        ("Sonsonate Centro", [
            "Sonsonate", "Sonzacate", "Nahulingo", "San Antonio del Monte", "Santo Domingo de Guzmán",
        ]),
        ("Sonsonate Este", [
            "Armenia", "Caluco", "Cuisnahuat", "Izalco", "San Julián", "Santa Isabel Ishuatán",
        ]),
        ("Sonsonate Oeste", ["Acajutla"]),
    ]),
    ("SV-US", "Usulután", [
        ("Usulután Norte", [
            "Alegría", "Berlín", "El Triunfo", "Estanzuelas", "Jucuapa", "Mercedes Umaña",
            "Nueva Granada", "San Buenaventura", "Santiago de María",
        ]),
        ("Usulután Este", [
            "California", "Concepción Batres", "Ereguayquín", "Jucuarán", "Ozatlán",
            "Santa Elena", "San Dionisio", "Santa María", "Tecapán", "Usulután",
        ]),
        ("Usulután Oeste", ["Jiquilisco", "Puerto El Triunfo", "San Agustín", "San Francisco Javier"]),
    ]),
]


def cargar_territorio(apps, schema_editor):
    Departamento = apps.get_model("pacientes", "Departamento")
    Municipio = apps.get_model("pacientes", "Municipio")
    Distrito = apps.get_model("pacientes", "Distrito")
    for codigo, nombre_departamento, municipios in TERRITORIO:
        departamento, _ = Departamento.objects.get_or_create(
            codigo=codigo, defaults={"nombre": nombre_departamento}
        )
        for nombre_municipio, distritos in municipios:
            municipio, _ = Municipio.objects.get_or_create(
                nombre=nombre_municipio, defaults={"departamento": departamento}
            )
            for nombre_distrito in distritos:
                Distrito.objects.get_or_create(municipio=municipio, nombre=nombre_distrito)


def borrar_territorio(apps, schema_editor):
    apps.get_model("pacientes", "Distrito").objects.all().delete()
    apps.get_model("pacientes", "Municipio").objects.all().delete()
    apps.get_model("pacientes", "Departamento").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pacientes", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(cargar_territorio, borrar_territorio),
    ]
