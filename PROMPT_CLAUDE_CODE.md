# Prompt para Claude Code — Editores de dibujo de AnimaLinux

Pega esto en Claude Code, dentro de la carpeta del proyecto `animalinux`.

---

Estoy trabajando en **AnimaLinux**, una app de mascotas animadas de escritorio para
**Arch Linux + Hyprland (Wayland)**, shell Caelestia. Está en Python con GTK4 +
gtk4-layer-shell. NO debe depender de servicios externos, cuentas ni internet
(solo, opcionalmente, rembg que ya se baja una vez). Todo local.

## Estado actual del proyecto (ya funciona)

Paquete `animalinux/` con estos módulos:
- `app.py` — GtkApplication (instancia única, daemon, bandeja, IPC por línea de comandos).
- `overlay.py` — ventana wlr-layer-shell por mascota; modos "gif" y "life"
  (camina, salta, saluda, se enoja, rebota; usa poses).
- `control.py` — ventana de configuración con 2 botones: «Crear animación» y
  «Crear animación con vida», más importar carpeta/pack/spritesheet.
- `importer.py` — carga gif/webp/apng/png/mp4, quita fondo (rembg isnet-anime o
  croma), límites de seguridad, genera frames espejados (flip_*.png).
- `library.py` — persistencia JSON. Cada animación: id, name, fps, mode,
  poses[], rig{}, on_desktop, x, y, scale. Frames en
  `~/.local/share/animalinux/animations/<id>/` (capa plana = pose "default";
  subcarpetas = poses walk/idle/greet/jump/angry, cada una con frame_*.png + flip_*.png).
- `procedural.py` — genera poses deformando la imagen (sin IA).
- `puppet.py` + `rigeditor.py` — animación por partes (marcar brazos/piernas y rotarlas).
- `framedit.py` + `frameditor.py` — editor frame por frame por TRANSFORMACIONES
  (mover/rotar/escalar/voltear cada cuadro, o importar un dibujo por cuadro) +
  validador + papel cebolla + reproducir + guardar como pose. Modo "guiado" con tips.
- `tips.py` — consejos de animación por acción.
- `pack.py` — formato `.alpack` (zip con mascot.json + poses/) importar/exportar.
- `folderimport.py` — importar mascota de Vida desde carpeta con validación.
- `spritesheet.py` — cortar tiras de sprites en frames.

## Lo que quiero que construyas: DOS editores de DIBUJO

Hoy el editor frame-a-frame solo transforma la imagen; quiero editores donde se
DIBUJE de verdad, pose por pose. Dos modos:

### 1) Editor de PÍXELES (estilo Piskel)
- Lienzo de tamaño configurable en píxeles (p.ej. 32x32, 64x64, 128x128); a mayor
  tamaño, más resolución/calidad.
- Herramientas: lápiz, borrador, balde (relleno), cuentagotas, selector de color
  y paleta. Tamaño de pincel 1-4 px.
- Cuadrícula visible y zoom.
- Fotogramas en una tira lateral: añadir, **duplicar** (capturar y seguir
  editando), borrar, reordenar, papel cebolla del cuadro anterior.
- Reproducir la animación con fps.
- Undo/redo.

### 2) Editor PAINT (pincel libre, no por celdas)
- Igual que el de píxeles pero con pincel suave de tamaño/opacidad variable, para
  dibujo más libre y de mayor resolución.
- Poder **cargar una imagen como base** y dibujar encima (volverla editable).
- "Capturar fotograma": guarda el estado actual como un cuadro, lo duplica y
  sigues modificando para el siguiente cuadro.

### Requisitos comunes
- Opción de **empezar en lienzo en blanco** (no obligar a importar).
- Guardar cada animación como una **pose** en la estructura existente:
  `frames_dir/<pose>/frame_0000.png ...` y luego llamar
  `importer.ensure_flipped(carpeta_pose)` y `app.register_pose(anim_id, pose, fps)`.
- Integrarse con los 2 botones: «Crear animación con vida» debe poder abrir estos
  editores para crear cada acción (usa `tips.py` para guiar y `tips.next_missing`).
- GTK4. Para el lienzo usa `Gtk.DrawingArea` + cairo; guarda los píxeles en una
  estructura propia (lista/np.array) y renderiza; exporta a PNG RGBA con Pillow.
- NADA de internet, cuentas ni servicios. Solo Python + GTK + Pillow (+ numpy si
  ayuda al lienzo).

## Cómo trabajar
1. Primero corre la app (`pip install --user --break-system-packages .` y
   `animalinux --show`) y revisa que todo lo actual funcione en mi Hyprland;
   arregla cualquier error de ejecución que aparezca (sobre todo de
   gtk4-layer-shell, layer-shell, o el editor frame-a-frame).
2. Crea `pixeleditor.py` y `painteditor.py` (o un editor unificado con un toggle
   de modo). Añade botones en `control.py` para abrirlos.
3. Hazlo por partes y prueba cada herramienta en pantalla. Implementa undo/redo.
4. Mantén el estilo del proyecto (comentarios en español, código claro).

Empieza revisando el estado actual y proponiéndome un plan antes de codear.
