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
### GIF sin vida (kaoruko, lacrimosa, herta, noce)
- Sin problemas de tamaño, pero el bucle salta al reiniciar. Opción: **cruce suave** o recortar al mejor punto de corte (buscar el par de cuadros con menor diferencia).

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
- Cambiar de pose no altera la escala ni la posición de los pies (deriva < 2 px).
- Sin cuadros idénticos consecutivos guardados como archivos.
- Kaoruko ≤ 3 MB en disco sin pérdida visible; RAM del overlay medida antes/después.
- `python tools/audit/audit.py` sin avisos en las mascotas de ejemplo.

## Ojo
- Tests/experimentos: aislar con `XDG_DATA_HOME` y `XDG_CONFIG_HOME` propios; nunca escribir en la biblioteca real.
- Nunca `rm -rf` de carpetas de la biblioteca sin confirmar con el usuario.
