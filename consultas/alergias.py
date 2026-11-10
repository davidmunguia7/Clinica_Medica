"""Aviso de alergias al recetar.

Compara, sin tildes ni mayúsculas, las palabras de las alergias anotadas en el
historial con el nombre de cada medicamento. Es una ayuda, no un sistema
experto: avisa «Penicilina» al recetar «Penicilina benzatínica», pero no sabe que
la amoxicilina es de la misma familia. El médico siempre decide.
"""
from pacientes.models import normalizar_busqueda

# Palabras que aparecen al anotar alergias pero no nombran ninguna sustancia
IGNORADAS = {
    "alergia", "alergias", "alergico", "alergica", "alergicos", "alergicas", "refiere", "niega",
    "ninguna", "ninguno", "conocida", "conocidas", "conocido", "conocidos", "medicamento",
    "medicamentos", "tiene", "presenta", "reaccion", "leve", "grave", "severa", "piel",
    "para", "como", "otros", "otras",
}


def palabras_clave(texto):
    """Palabras de 4 letras o más que no están en IGNORADAS."""
    return {p for p in normalizar_busqueda(texto).split() if len(p) >= 4 and p not in IGNORADAS}


def coincidencias(alergias, nombres):
    """[(nombre del medicamento, [palabras de la alergia que coinciden])] para los que parecen chocar."""
    claves = palabras_clave(alergias)
    if not claves:
        return []
    resultado = []
    for nombre in nombres:
        normalizado = normalizar_busqueda(nombre)
        encontradas = sorted(clave for clave in claves if clave in normalizado)
        if encontradas:
            resultado.append((nombre, encontradas))
    return resultado
