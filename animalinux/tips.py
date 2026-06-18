"""
Guía de animación: tips por acción para el modo "Crear animación con vida".

No es IA: son consejos prácticos de animación para que el usuario arme cada
acción en el editor frame por frame. La app muestra estos tips y sugiere cuántos
cuadros y qué hacer en cada pose.
"""

# orden sugerido en que la app pide crear las acciones
GUIDED_ORDER = ["default", "idle", "walk", "greet", "jump", "angry", "grab"]

# Consejos generales que aplican a cualquier pose (se muestran al principio)
GENERAL_TIPS = [
    "Dibuja siempre sobre la MISMA silueta base para que la mascota no «salte» entre poses.",
    "Mantén los pies a la misma altura (la línea del suelo) salvo en el salto.",
    "Para un bucle suave, el último cuadro debe enlazar con el primero.",
    "Guarda cada pose antes de cerrar; podrás volver y añadir más después.",
]

TIPS = {
    "default": {
        "titulo": "Pose base (quieta)",
        "frames": 1,
        "tips": [
            "Es la pose neutral, mirando al frente o de costado.",
            "Asegúrate de que los pies queden apoyados en la parte de abajo del lienzo.",
            "Con 1 solo cuadro basta; será la base de TODAS las demás acciones.",
            "Céntrala horizontalmente y deja poco margen vacío alrededor.",
            "Consejo: duplica esta pose como punto de partida para las otras.",
        ],
    },
    "idle": {
        "titulo": "Reposo (respira)",
        "frames": 4,
        "tips": [
            "4-6 cuadros con un movimiento mínimo: que parezca que respira.",
            "Sube/baja el cuerpo 1-2 px o escálalo un 2-3 % (pecho que se infla).",
            "El primer y el último cuadro casi iguales → bucle sin saltos.",
            "Mueve solo el torso/cabeza; los pies quedan fijos en el suelo.",
            "Hazlo lento (FPS bajo, 6-8) para que se vea relajado.",
        ],
    },
    "walk": {
        "titulo": "Caminar",
        "frames": 8,
        "tips": [
            "6-8 cuadros alternando pierna adelante / pierna atrás.",
            "Pies SIEMPRE a la misma altura del suelo (si no, parece que patina).",
            "Sube el cuerpo 2-3 px a mitad del paso (rebote) y bájalo al apoyar.",
            "Los brazos se balancean al revés que las piernas (brazo izq. con pierna der.).",
            "El pie de apoyo se desplaza hacia atrás; el otro avanza por el aire.",
            "Empieza por las poses clave (contacto y paso) y rellena el resto.",
        ],
    },
    "greet": {
        "titulo": "Saludar",
        "frames": 6,
        "tips": [
            "Levanta un brazo y agítalo 2-3 veces (sube/baja la mano).",
            "Inclina un poco la cabeza o el cuerpo para dar energía.",
            "6 cuadros bastan; mantén las piernas quietas.",
            "Una sonrisa o los ojos cerrados ayudan a que se vea amistoso.",
            "Vuelve a la pose base en el último cuadro para enlazar.",
        ],
    },
    "jump": {
        "titulo": "Saltar",
        "frames": 6,
        "tips": [
            "Anticipación: agáchate (squash) aplastando un poco el cuerpo.",
            "En el aire estíralo (stretch) hacia arriba.",
            "Sube el cuerpo bastante (40-80 px) en el cuadro más alto.",
            "Al caer vuelve a aplastar (squash) y recupera la pose base.",
            "Brazos hacia arriba en el impulso dan más sensación de salto.",
        ],
    },
    "angry": {
        "titulo": "Enojo",
        "frames": 6,
        "tips": [
            "Temblor rápido: pequeños movimientos de lado a lado (2-3 px).",
            "Inclina el cuerpo hacia adelante, con los brazos tensos.",
            "Cuadros cortos y rápidos (FPS alto) dan sensación de enfado.",
            "Ceño fruncido, boca apretada o vapor saliendo refuerzan el gesto.",
        ],
    },
    "grab": {
        "titulo": "Agarra el ratón",
        "frames": 6,
        "tips": [
            "Se activa cuando le das 4 clicks seguidos a la mascota.",
            "Brazos extendidos hacia adelante, como sujetando algo.",
            "Alterna 2 cuadros (brazo extendido / ligeramente doblado) en bucle.",
            "Expresión furiosa o traviesa — que se note que tiene el control.",
        ],
    },
}


def tip_for(pose):
    return TIPS.get(pose, {
        "titulo": pose, "frames": 4,
        "tips": [
            "Crea varios cuadros con cambios pequeños entre ellos.",
            "Mantén la silueta y la línea del suelo coherentes con la pose base.",
            "Guárdala antes de cerrar para poder seguir editándola luego.",
        ],
    })


def next_missing(poses_done):
    """Sugiere la siguiente acción a crear, en orden recomendado."""
    for p in GUIDED_ORDER:
        if p not in poses_done:
            return p
    return None
