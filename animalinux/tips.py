"""
Guía de animación: tips por acción para el modo "Crear animación con vida".

No es IA: son consejos prácticos de animación para que el usuario arme cada
acción en el editor frame por frame. La app muestra estos tips y sugiere cuántos
cuadros y qué hacer en cada pose.
"""

# orden sugerido en que la app pide crear las acciones
from .i18n import N_, tr

GUIDED_ORDER = ["default", "idle", "walk", "greet", "jump", "angry", "grab"]

# Consejos generales que aplican a cualquier pose (se muestran al principio)
GENERAL_TIPS = [
    N_("Dibuja siempre sobre la MISMA silueta base para que la mascota no «salte» entre poses."),
    N_("Mantén los pies a la misma altura (la línea del suelo) salvo en el salto."),
    N_("Para un bucle suave, el último cuadro debe enlazar con el primero."),
    N_("Guarda cada pose antes de cerrar; podrás volver y añadir más después."),
]

TIPS = {
    "default": {
        "titulo": N_("Pose base (quieta)"),
        "frames": 1,
        "tips": [
            N_("Es la pose neutral, mirando al frente o de costado."),
            N_("Asegúrate de que los pies queden apoyados en la parte de abajo del lienzo."),
            N_("Con 1 solo cuadro basta; será la base de TODAS las demás acciones."),
            N_("Céntrala horizontalmente y deja poco margen vacío alrededor."),
            N_("Consejo: duplica esta pose como punto de partida para las otras."),
        ],
    },
    "idle": {
        "titulo": N_("Reposo (respira)"),
        "frames": 4,
        "tips": [
            N_("4-6 cuadros con un movimiento mínimo: que parezca que respira."),
            N_("Sube/baja el cuerpo 1-2 px o escálalo un 2-3 % (pecho que se infla)."),
            N_("El primer y el último cuadro casi iguales → bucle sin saltos."),
            N_("Mueve solo el torso/cabeza; los pies quedan fijos en el suelo."),
            N_("Hazlo lento (FPS bajo, 6-8) para que se vea relajado."),
        ],
    },
    "walk": {
        "titulo": "Caminar",
        "frames": 8,
        "tips": [
            N_("6-8 cuadros alternando pierna adelante / pierna atrás."),
            N_("Pies SIEMPRE a la misma altura del suelo (si no, parece que patina)."),
            N_("Sube el cuerpo 2-3 px a mitad del paso (rebote) y bájalo al apoyar."),
            N_("Los brazos se balancean al revés que las piernas (brazo izq. con pierna der.)."),
            N_("El pie de apoyo se desplaza hacia atrás; el otro avanza por el aire."),
            N_("Empieza por las poses clave (contacto y paso) y rellena el resto."),
        ],
    },
    "greet": {
        "titulo": "Saludar",
        "frames": 6,
        "tips": [
            N_("Levanta un brazo y agítalo 2-3 veces (sube/baja la mano)."),
            N_("Inclina un poco la cabeza o el cuerpo para dar energía."),
            N_("6 cuadros bastan; mantén las piernas quietas."),
            N_("Una sonrisa o los ojos cerrados ayudan a que se vea amistoso."),
            N_("Vuelve a la pose base en el último cuadro para enlazar."),
        ],
    },
    "jump": {
        "titulo": "Saltar",
        "frames": 6,
        "tips": [
            N_("Anticipación: agáchate (squash) aplastando un poco el cuerpo."),
            N_("En el aire estíralo (stretch) hacia arriba."),
            N_("Sube el cuerpo bastante (40-80 px) en el cuadro más alto."),
            N_("Al caer vuelve a aplastar (squash) y recupera la pose base."),
            N_("Brazos hacia arriba en el impulso dan más sensación de salto."),
        ],
    },
    "angry": {
        "titulo": "Enojo",
        "frames": 6,
        "tips": [
            N_("Temblor rápido: pequeños movimientos de lado a lado (2-3 px)."),
            N_("Inclina el cuerpo hacia adelante, con los brazos tensos."),
            N_("Cuadros cortos y rápidos (FPS alto) dan sensación de enfado."),
            N_("Ceño fruncido, boca apretada o vapor saliendo refuerzan el gesto."),
        ],
    },
    "grab": {
        "titulo": N_("Agarra el ratón"),
        "frames": 6,
        "tips": [
            N_("Se activa cuando le das 4 clicks seguidos a la mascota."),
            N_("Brazos extendidos hacia adelante, como sujetando algo."),
            N_("Alterna 2 cuadros (brazo extendido / ligeramente doblado) en bucle."),
            N_("Expresión furiosa o traviesa — que se note que tiene el control."),
        ],
    },
}


def tip_for(pose):
    raw = TIPS.get(pose, {
        "titulo": pose, "frames": 4,
        "tips": [
            N_("Crea varios cuadros con cambios pequeños entre ellos."),
            N_("Mantén la silueta y la línea del suelo coherentes con la pose base."),
            N_("Guárdala antes de cerrar para poder seguir editándola luego."),
        ],
    })
    return {"titulo": tr(raw["titulo"]), "frames": raw["frames"],
            "tips": [tr(x) for x in raw["tips"]]}


def next_missing(poses_done):
    N_("""Sugiere la siguiente acción a crear, en orden recomendado.""")
    for p in GUIDED_ORDER:
        if p not in poses_done:
            return p
    return None
