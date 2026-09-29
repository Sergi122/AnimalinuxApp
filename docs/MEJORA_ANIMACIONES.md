# Plan de optimización y calidad de animaciones (próxima sesión)

Auditoría hecha el 2026-09-29 sobre la biblioteca real (`~/.config/animalinux/library.json`,
datos en `~/.local/share/animalinux/animations`). Solo lectura: no se modificó ni borró nada.

## Cómo reproducir la auditoría
```
python tools/audit/audit.py --json docs/auditoria.json   # métricas + problemas por pose
cd /ruta/salida && python <repo>/tools/audit/sheets.py    # hojas de contacto visuales en ./sheets/
```
Métricas por animación/pose: cuadros, tamaño, peso, cuadros idénticos, movimiento medio entre cuadros,
**costura del bucle** (diferencia último→primero frente al movimiento medio), deriva de los pies,
borde semitransparente (halo) y peso por cuadro. Resultado completo: `docs/auditoria-2026-09-29.json`.

## Inventario (8 animaciones en biblioteca)
| Nombre | Modo | fps | Peso | Notas |
|---|---|---|---|---|
| kaoruko / lacrimosa / herta / noce | sin vida (GIF) | 10–13 | 0.6–3 MB | 12–20 cuadros; movimiento alto, **costura 1.5–2x el movimiento** (el GIF no cierra bien el bucle) |
| Ejemplo Vida | con vida | 5 | 1.2 MB | 7 poses, ver abajo |
| Gato Minecraft | con vida | 8 | 34 KB | 48×48, muchos cuadros repetidos |
| Gato Pixel | con vida | 12 | 72 KB | 48×48, poco movimiento real |
| Kaoruko | con vida | 12 | 7 MB | 9 poses, la más completa y la más pesada |

Además hay **~31 MB huérfanos** en `animations/` (7 carpetas sin entrada en la biblioteca:
`3f79661e9aeb`, `cadac6716d7d`, `fb4d026c3233`, `f9940882d665`, `gato_animado_v2`, y dos vacías `6263f8aa5e31`, `d60510522caf`).
**No borrar sin preguntar al usuario** (puede haber trabajo suyo). Proponer un comando/botón «Limpiar restos» que liste y confirme.

## Hallazgos por animación
### Ejemplo Vida (mascota azul)
- `angry`: 12 de 16 cuadros idénticos, prácticamente estática; costura x14 → **rehacer** (temblor + ceño, ver guías de tips.py).
- `greet` 8, `idle` 6, `sleep` 10, cuadros idénticos: se puede recortar o dar variación real (respiración, parpadeo).
- `jump`: los pies suben 80 px (correcto), pero falta squash/stretch al despegar y caer.
- `walk`: solo se ladea el cuerpo; **no hay ciclo de piernas** → parece que se desliza.
### Gato Pixel / Gato Minecraft (48×48)
- `idle` y `walk` se ven casi iguales; `walk` sin ciclo de patas claro. Muchos cuadros repetidos.
- Casi todas las poses tienen **costura de bucle 3–9x** el movimiento medio: el último cuadro no vuelve a la pose base.
- Resolución muy baja: al escalar en el escritorio conviene escalado *nearest* (sin suavizar) — comprobar que el overlay lo respeta.
### Kaoruko (con vida, 9 poses)
- La pose base (`default`, 312×990 de pie y de frente) no coincide con el resto (perfil, 150–250 px de ancho): **tamaños y encuadres distintos por pose** (149×248, 210×516, 246×495, 250×274…). El personaje «salta» de escala al cambiar de pose.
- `base` pesa 330 KB por cuadro; `walk` 1.8 MB, `fall` 1.5 MB (36 cuadros). Total 7 MB para una sola mascota.
- Se ve una **línea fina de suelo** bajo algunos cuadros (angry/fall/grab): confirmar que es artefacto del origen y eliminarla.
- Bucles sin cerrar (costura 30–55 con movimiento 14–30).
### Animaciones sin vida (GIF): kaoruko, lacrimosa, herta, noce
Las cuatro son chibis bailando (arte HD con contorno), importadas de GIF a 10–13 fps.

| Nombre | Cuadros / fps / duración | Tamaño | Peso | Movimiento entre cuadros | Costura del bucle | Mejor corte posible | Deriva horizontal | Halo |
|---|---|---|---|---|---|---|---|---|
| kaoruko | 20 / 13 / 1.5 s | 443×454 | 3.0 MB | 28 | 42 | cuadros 1→16 (21) | 63 px | 2 % |
| lacrimosa | 20 / 13 / 1.5 s | 183×183 | 0.6 MB | 31 | 58 | cuadros 2→16 (35) | 37 px | **8 %** |
| herta | 12 / 10 / 1.2 s | 414×338 | 0.9 MB | 39 | 58 | cuadros 3→9 (44) | 61 px | 2 % |
| noce | 20 / 13 / 1.5 s | 289×292 | 1.5 MB | **49** | **82** | cuadros 4→19 (39) | 45 px | 0 % |

Lectura de las cifras (diferencia media de píxeles 0–255 entre cuadros consecutivos):
- **Movimiento muy alto entre cuadros (28–49):** con solo 10–13 fps y 12–20 cuadros, cada paso es un salto grande → la animación se ve **entrecortada**. Es el problema principal de estas cuatro, más que el bucle.
- **Costura 1.4–1.7x el movimiento** (noce 1.7x): el último cuadro no enlaza con el primero. Buscar otro punto de corte ayuda poco (la mejor pareja sigue siendo tan lejana como un paso normal) porque son coreografías completas: el arreglo real es **generar cuadros intermedios** entre el último y el primero.
- **herta** (12 cuadros, 10 fps): la cabeza gira de frente a espalda/perfil en pocos cuadros; es la más brusca y la de menor duración.
- **lacrimosa** es la única con halo notable (8 % de píxeles semitransparentes en el borde): probable recorte con IA o fondo mal quitado; revisar el borde sobre fondo claro y oscuro.
- **Encuadre:** el personaje se desplaza 37–63 px de lado a lado (coreografía), pero el lienzo no tiene margen fijo; comprobar que nada se recorta en los extremos y fijar el pie de referencia para que no «flote» en el escritorio.
- **Peso:** kaoruko 3 MB para 1.5 s; se puede bajar mucho con cuantización o WebP sin pérdida (arte plano).

Acciones específicas para sin vida:
1. **Interpolación de cuadros** (tweening por flujo óptico o morphing simple) para duplicar los cuadros (→ 24 fps efectivos) sin rehacer el arte; empezar por herta y noce.
2. **Cierre de bucle**: insertar 2–4 cuadros intermedios entre el último y el primero, o modo «ida y vuelta» automático para las que no sean cíclicas.
3. **Limpiar halo** de lacrimosa (des-matte del borde/erosión de 1 px del alfa).
4. **Reducir peso** de kaoruko (cuantizar/WebP) y guardar duración por cuadro en vez de repetir PNG.
5. Mostrar en la ficha de la mascota un indicador «Suavidad» (movimiento/fps) y «Cierre de bucle» con los mismos números de esta tabla.

## Plan de trabajo propuesto (por prioridad)
1. **Normalizar poses** (mayor impacto visual): misma altura de referencia y mismo ancla de pies (centro-abajo) para todas las poses de una mascota; recorte al contenido con margen común. Herramienta en el importador y botón «Normalizar» por mascota.
2. **Reparar bucles**: detectar mejor punto de corte (min diff), opción de *cross-fade* de N cuadros y de «ida y vuelta» automático; mostrar la métrica de costura en el editor.
3. **Quitar duplicados y aplicar exposición**: colapsar cuadros idénticos consecutivos guardando duración por cuadro (en vez de repetir PNG) → menos peso y menos trabajo en el overlay.
4. **Peso y rendimiento**: cuantizar PNG (pngquant/`Image.quantize`) para arte plano, o usar atlas WebP sin pérdida; cargar poses a demanda y liberar las que no se usan; medir RAM del overlay con varias mascotas (Kaoruko a 7 MB de PNG ocupa mucho más descomprimida).
5. **Calidad del movimiento con vida**: plantillas de ciclo para `walk` (contacto/paso/contacto), squash&stretch en `jump`, respiración y parpadeo en `idle`, transición suave entre poses (ya hay guías en `tips.py` para reutilizar).
6. **Escalado**: respetar *nearest* para pixel art y *bilinear* para arte HD; tamaño lógico configurable por mascota.
7. **Limpieza de huérfanos** con confirmación (ver arriba) y comprobación de integridad en el arranque (biblioteca ↔ carpetas).
8. Añadir la auditoría como comando: `animalinux --audit` y como pestaña «Salud» en la ficha de cada mascota.

## Criterios de aceptación
- Ninguna pose con costura > 2x el movimiento medio, salvo `jump`/`fall`.
- GIF sin vida: movimiento entre cuadros < 15 tras interpolar (≈24 fps efectivos) y costura ≤ 1x el movimiento.
- Cambiar de pose no altera la escala ni la posición de los pies (deriva < 2 px).
- Sin cuadros idénticos consecutivos guardados como archivos.
- Kaoruko ≤ 3 MB en disco sin pérdida visible; RAM del overlay medida antes/después.
- `python tools/audit/audit.py` sin avisos en las mascotas de ejemplo.

## Ojo
- Tests/experimentos: aislar con `XDG_DATA_HOME` y `XDG_CONFIG_HOME` propios; nunca escribir en la biblioteca real.
- Nunca `rm -rf` de carpetas de la biblioteca sin confirmar con el usuario.
