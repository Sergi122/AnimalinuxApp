"""
Guía de animación: tips por acción para el modo "Crear animación con vida".

No es IA: son consejos prácticos de animación para que el usuario arme cada
acción en el editor frame por frame. La app muestra estos tips y sugiere cuántos
cuadros y qué hacer en cada pose.
"""

# orden sugerido en que la app pide crear las acciones
GUIDED_ORDER = ["default", "idle", "walk", "greet", "jump", "angry", "grab"]

TIPS = {
    "default": {
        "titulo": "Pose base (quieta)",
        "frames": 1,
        "tips": [
            "Es la pose neutral, mirando al frente o de costado.",
            "Asegúrate de que los pies queden apoyados en la parte de abajo.",
            "Con 1 solo cuadro basta; será la base de las demás acciones.",
        ],
    },
    "idle": {
        "titulo": "Reposo (respira)",
        "frames": 4,
        "tips": [
            "4-6 cuadros con un movimiento mínimo: que respire.",
            "Sube/baja el cuerpo 1-2 px o escálalo un 2-3 %.",
            "Que el primer y último cuadro sean casi iguales para un bucle suave.",
        ],
    },
    "walk": {
        "titulo": "Caminar",
        "frames": 8,
        "tips": [
            "6-8 cuadros alternando pierna adelante / pierna atrás.",
            "Mantén los pies a la MISMA altura (si no, parece que patina).",
            "Sube el cuerpo 2-3 px en el paso (rebote) y bájalo al apoyar.",
            "Los brazos se mueven al revés que las piernas.",
        ],
    },
    "greet": {
        "titulo": "Saludar",
        "frames": 6,
        "tips": [
            "Levanta el brazo y agítalo 2-3 veces (sube/baja).",
            "Inclina un poco la cabeza o el cuerpo para dar energía.",
            "6 cuadros suelen bastar; no muevas las piernas.",
        ],
    },
    "jump": {
        "titulo": "Saltar",
        "frames": 6,
        "tips": [
            "Agáchate (squash) antes de saltar: aplasta un poco el cuerpo.",
            "En el aire estíralo (stretch) y al caer vuelve a aplastar.",
            "Sube el cuerpo bastante (40-80 px) en el cuadro más alto.",
        ],
    },
    "angry": {
        "titulo": "Enojo",
        "frames": 6,
        "tips": [
            "Temblor rápido: pequeños movimientos de lado a lado.",
            "Inclina el cuerpo hacia adelante, brazos tensos.",
            "Cuadros cortos y rápidos dan sensación de enfado.",
        ],
    },
    "grab": {
        "titulo": "Agarra el ratón",
        "frames": 6,
        "tips": [
            "Se activa cuando le das 4 clicks seguidos.",
            "Brazos extendidos hacia adelante, como sujetando algo.",
            "Puedes alternar 2 cuadros (brazo extendido / ligeramente doblar) en bucle.",
            "Expresión furiosa o traviesa — que se note que tiene el control.",
        ],
    },
}


def tip_for(pose):
    return TIPS.get(pose, {
        "titulo": pose, "frames": 4,
        "tips": ["Crea varios cuadros con cambios pequeños entre ellos."],
    })


def next_missing(poses_done):
    """Sugiere la siguiente acción a crear, en orden recomendado."""
    for p in GUIDED_ORDER:
        if p not in poses_done:
            return p
    return None
