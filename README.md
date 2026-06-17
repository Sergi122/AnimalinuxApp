# AnimaLinux

Mascotas animadas en tu escritorio para **Hyprland (Wayland)**, con editor de
**píxeles** estilo Aseprite y editor de **pintura** estilo Clip Studio Paint.
Importa un GIF/vídeo o dibuja tus propias poses, quita el fondo y deja solo la
mascota flotando sobre el escritorio. Múltiples mascotas, física de rebote,
saludos, emociones y más.

🌐 **Descarga y comparte animaciones en la comunidad:** [sergi122.github.io/Animalinux](https://sergi122.github.io/Animalinux)

---

## Características

| Módulo | Qué hace |
|---|---|
| **Control** | Ventana principal — Normal (GIF) y Con vida (camina, salta, saluda) |
| **Editor de píxeles** | Estilo Aseprite: lápiz, relleno, outline, línea, dither, simetría, varita, selección, 48 colores |
| **Editor de pintura** | Estilo Clip Studio Paint: 12 pinceles, 10 blend modes, capas, zoom continuo, simetría, smudge, gradiente, vectorial, timeline, audio, exportar GIF/MP4 |
| **Overlay** | Ventana layer-shell transparente por mascota, 6 poses, física real |
| **Packs (.alpack)** | Importar/exportar personajes completos con todas sus poses |

---

## Instalación rápida (Arch Linux)

```bash
git clone https://github.com/Sergi122/AnimalinuxApp.git
cd animalinux
chmod +x install.sh
./install.sh
```

### Dependencias

```bash
# Obligatorias
sudo pacman -S python python-gobject gtk4 python-pillow gtk4-layer-shell \
               libayatana-appindicator

# Muy recomendadas (mejor rendimiento)
sudo pacman -S python-numpy

# Opcionales
sudo pacman -S mpv ffmpeg                          # audio y exportar MP4
pip install --user --break-system-packages rembg onnxruntime  # recorte IA
```

### Reinstalar después de editar el código

```bash
cd /home/maomao/Downloads/animalinux
pip install --user --break-system-packages .
pkill -f animalinux; sleep 1
ANIMALINUX_PRELOADED=1 nohup animalinux --show > /tmp/animalinux.log 2>&1 &
```

---

## Uso

```bash
animalinux --show     # abrir ventana de configuración
animalinux --daemon   # solo el servicio en segundo plano (autostart)
animalinux --quit     # cerrar todo
```

---

## Editor de píxeles — Guía rápida

Abre desde **Control → Nueva animación → Píxel art** o con el botón **🎨 Editar**.

### Interfaz

```
┌─[Toolbar: zoom · FPS · ▶ · 👁 cebolla · simetría ↔↕✦ · undo/redo · ❓]────┐
│ [Herramientas] │          LIENZO DE PÍXELES         │ [Frames]             │
│  ✏ Lápiz  B   │  (zoom con Ctrl+Scroll o +/-)       │  + Nuevo             │
│  ⬜ Borrador E │  (pan con botón medio)              │  ⎘ Duplicar          │
│  🪣 Relleno F  │                                     │  [thumb F1]          │
│  R O L C V D W│                                     │  [thumb F2] ←actual  │
│  S M I         │                                     │  …                   │
│  [48 colores]  │                                     │                      │
└─[Status: X:— Y:— · color · zoom% · tamaño · pose · 💾 Guardar pose]────────┘
```

### Atajos de teclado

| Tecla | Acción |
|---|---|
| `B` | Lápiz |
| `E` | Borrador |
| `F` | Relleno |
| `R` | Reemplazar color |
| `O` | Outline rect |
| `L` | Línea |
| `C` / `V` | Elipse ○ / ● |
| `D` | Dithering |
| `W` | Varita mágica |
| `S` / `M` | Selección / Mover |
| `I` | Cuentagotas |
| `[ ]` | Tamaño del lápiz |
| `Ctrl+Z/Y` | Deshacer / Rehacer |
| `Ctrl+S` | Guardar pose |
| `Ctrl+C/V` | Copiar / Pegar frame |
| `Ctrl+N/D` | Nuevo / Duplicar frame |
| `Espacio` | Reproducir / Pausar |

### Guardar

1. Escribe el nombre de la pose en el campo inferior (ej: `walk`)
2. Pulsa **💾 Guardar pose** o `Ctrl+S`

---

## Editor de pintura — Guía rápida

Abre desde **Control → Nueva animación → Dibujo libre** o con **🖌️ Editar**.

### Interfaz (estilo Clip Studio Paint)

```
┌─[Toolbar: zoom · FPS · ▶ · 👁 cebolla · ✋ estab · sim ↔↕✦ · 〜 suave · 🎥 · 🎵 · ❓]─┐
├─[Opciones: Pincel▾ · Radio · Suavidad · Opacidad · Varita tol.]──────────────────────────┤
│ [Herram.] │              LIENZO                    │ [Capas]                              │
│  grid 2×8 │  Ctrl+Scroll = zoom (0.05×–32×)       │  + ⎘ ↓⊡ ⊡ 🗑                       │
│  FG · BG  │  Espacio+drag = pan                   │  thumb 👁 🔒 α  Nombre               │
│  ⇌ swap   │  B E F G L I S M W V = herramientas   │  blend mode · opacidad               │
│  #hex     │  X = cambiar FG↔BG                    │                                      │
│  H S V    │                                        │                                      │
│ [recientes│                                        │                                      │
├─[Timeline: ➕ ⎘ 🗑 | ⎘Copiar ⎘Pegar | 🎬GIF 🎬MP4 | ← [F1][F2][F3]... →]────────────┤
└─[Status: X:— Y:— · RGBA · zoom% · tamaño · pose · 💾 Guardar pose]─────────────────────┘
```

### Tipos de pincel

| Nombre | Efecto |
|---|---|
| Redondo suave | Pincel estándar con borde suave |
| Lápiz (duro) | Borde duro, sin anti-alias |
| Aerógrafo | Dispersión gaussiana suave |
| Textura | Ruido aleatorio con borde |
| Tiza | Granulado irregular |
| Acuarela | Borde mojado semi-transparente |
| Marcador | Cobertura plana |
| Crayón | Rayas diagonales características |
| Esponja | Puntos dispersos superpuestos |
| Píxel exacto | Círculo sin anti-aliasing |
| Abanico | Rayas radiales en semicírculo |
| Tinta (pluma) | Punta elíptica de tinta |

### Blend modes de capa

Normal · Multiplicar · Pantalla · Superponer · Añadir · Diferencia · Luz dura · Luz suave · Eludir color · Quemar color

### Atajos de teclado

| Tecla | Acción |
|---|---|
| `B/E/F/G/L` | Pincel / Borrador / Relleno / Gradiente / Línea |
| `I/S/M/W/V` | Cuentagotas / Selección / Mover / Varita / Vectorial |
| `X` | Cambiar FG ↔ BG |
| `[ ]` | Tamaño del pincel |
| `Ctrl+Z/Y` | Deshacer / Rehacer (30 niveles) |
| `Ctrl+S` | Guardar pose |
| `Ctrl+C/V` | Copiar / Pegar frame |
| `Ctrl+N/D` | Nuevo / Duplicar frame |
| `Ctrl+0` | Ajustar zoom |
| `Espacio+drag` | Pan (desplazar vista) |
| `Espacio` | Reproducir / Pausar |

---

## Animaciones con vida — Poses y carpetas

Una mascota **con vida** necesita poses que la app reproduce según su estado.

### Poses disponibles

| Nombre | Cuadros recomendados | Cuándo se usa |
|---|---|---|
| `default` | 1–2 | Parada, sin acción (obligatoria) |
| `idle` | 4–6 | Quieta, respirando |
| `walk` | 6–8 | Caminando por la pantalla |
| `greet` | 6 | Al pasar el cursor encima |
| `jump` | 6 | Salto físico / rebote |
| `angry` | 6 | Al hacer clic varias veces |

Solo `default` es obligatoria. Si falta alguna otra, la app usa `default`.

### Crear poses en el editor

1. Abre el editor (píxeles o pintura)
2. Dibuja los frames de la acción
3. Escribe el nombre de la pose en el campo inferior (`walk`, `idle`…)
4. Pulsa **💾 Guardar pose** o `Ctrl+S`
5. El editor te sugiere automáticamente la siguiente pose faltante

### Importar desde carpeta

Si tienes los PNGs listos, usa **Con vida → Importar carpeta de mascota**:

```
mi_mascota/
├── default/
│   ├── frame_0000.png
│   └── frame_0001.png
├── idle/
│   ├── frame_0000.png
│   ├── frame_0001.png
│   ├── frame_0002.png
│   └── frame_0003.png
├── walk/
│   └── frame_0000.png … frame_0007.png
├── greet/
│   └── frame_0000.png … frame_0005.png
├── jump/
│   └── frame_0000.png … frame_0005.png
└── angry/
    └── frame_0000.png … frame_0005.png
```

**Requisitos:**
- Imágenes PNG con fondo transparente (modo RGBA)
- Todos los frames de una pose deben tener el mismo tamaño
- Los archivos se llaman `frame_0000.png`, `frame_0001.png`, etc.

### Generación automática de poses

Si solo tienes `default`, pulsa **⚙️ Generar poses** en la fila de la mascota.
La app deforma la imagen base para crear las demás poses. El resultado es básico;
edítalo luego para animaciones más expresivas.

---

## Subir a GitHub

```bash
# 1. Inicializar repositorio (primera vez)
cd /home/maomao/Downloads/animalinux
git init
git remote add origin https://github.com/Sergi122/AnimalinuxApp.git

# 2. Commit y push
git add .
git commit -m "descripción del cambio"
git push -u origin main

# 3. Cambios posteriores
git add .
git commit -m "descripción"
git push
```

### Crear release con tag de versión

```bash
git tag v0.1.0
git push origin v0.1.0
```

---

## Publicar en AUR

### Requisitos previos

```bash
# Instalar herramientas AUR
sudo pacman -S base-devel

# Generar clave SSH para AUR (si no tienes)
ssh-keygen -t ed25519 -C "tu@email.com"
# Sube la clave pública en: https://aur.archlinux.org/account/
```

### Subir el paquete

```bash
# 1. Clonar tu repositorio AUR (primera vez)
git clone ssh://aur@aur.archlinux.org/animalinux.git aur-animalinux
cd aur-animalinux

# 2. Copia el PKGBUILD del proyecto
cp /home/maomao/Downloads/animalinux/PKGBUILD .

# 3. Edita PKGBUILD: pon tu nombre, email y URL de GitHub correcta
#    Calcula el sha256sum cuando tengas el release en GitHub:
#    curl -L https://github.com/Sergi122/AnimalinuxApp/archive/v0.1.0.tar.gz | sha256sum

# 4. Genera el .SRCINFO (obligatorio para AUR)
makepkg --printsrcinfo > .SRCINFO

# 5. Prueba que compila correctamente
makepkg -si

# 6. Sube a AUR
git add PKGBUILD .SRCINFO
git commit -m "Initial release v0.1.0"
git push
```

### Actualizar el paquete en AUR

```bash
cd aur-animalinux
# Edita PKGBUILD: actualiza pkgver y pkgrel
# Recalcula sha256sum con la nueva URL del tarball
makepkg --printsrcinfo > .SRCINFO
makepkg -si   # prueba local
git add PKGBUILD .SRCINFO
git commit -m "Update to v0.X.Y"
git push
```

---

## Archivos del proyecto

| Archivo | Qué hace |
|---|---|
| `app.py` | GtkApplication principal: daemon, mascotas, bandeja |
| `control.py` | Ventana de configuración (pestañas Normal / Con vida) |
| `pixeleditor.py` | Editor de píxeles estilo Aseprite |
| `painteditor.py` | Editor de pintura estilo Clip Studio Paint |
| `overlay.py` | Ventana transparente layer-shell por mascota |
| `library.py` | Base de datos JSON de animaciones |
| `importer.py` | Importa gif/mp4, quita fondo |
| `settings.py` | Configuración persistente del usuario |
| `tips.py` | Guías de animación por pose |
| `theme.py` | Tema oscuro GTK4 (prioridad USER) |
| `pack.py` | Formato .alpack (zip de poses) |
| `procedural.py` | Genera poses deformando la imagen base |
| `PKGBUILD` | Receta para publicar en AUR |

---

## Solución de problemas

| Problema | Solución |
|---|---|
| `animalinux: command not found` | Añade `export PATH="$HOME/.local/bin:$PATH"` al `.bashrc` |
| No se ve la mascota / sale con marco | Falta precargar `gtk4-layer-shell`. La app se relanza sola; verifica que el paquete esté instalado |
| El recorte se comió partes del personaje | Usa el método **IA** (requiere rembg + onnxruntime) |
| `Gdk-WARNING Cannot get portal` | Normal en Hyprland sin xdg-desktop-portal — no afecta nada |
| La app no arranca (exit code 144) | Otra instancia ya corre — ejecuta `animalinux --quit` primero |
| Los tutoriales no aparecen | Borra `~/.config/animalinux/settings.json` para reiniciarlos |
| No se exporta MP4 | Instala `ffmpeg`: `sudo pacman -S ffmpeg` |
| No hay audio en el editor | Instala `mpv`: `sudo pacman -S mpv` |
