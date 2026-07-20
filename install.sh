#!/usr/bin/env bash
# Instalador de AnimaLinux. Funciona en Hyprland/Sway (Wayland) y en
# GNOME/Cinnamon/MATE/Xfce (X11 o Wayland vía XWayland): detecta el gestor
# de paquetes y solo instala gtk4-layer-shell donde aplica (Arch/Hyprland).
set -e

PKG_MGR=""
if command -v pacman &>/dev/null; then
    PKG_MGR="pacman"
elif command -v apt &>/dev/null; then
    PKG_MGR="apt"
elif command -v dnf &>/dev/null; then
    PKG_MGR="dnf"
elif command -v zypper &>/dev/null; then
    PKG_MGR="zypper"
else
    echo "!! No reconozco tu gestor de paquetes (pacman/apt/dnf/zypper)."
    echo "   Instala manualmente: python3, gi (PyGObject), GTK4, Pillow,"
    echo "   python-xlib, y opcionalmente libwnck y libayatana-appindicator."
fi

echo ">> Instalando dependencias del sistema ($PKG_MGR)..."
case "$PKG_MGR" in
    pacman)
        sudo pacman -S --needed --noconfirm \
            gtk4 python-gobject python-pillow python-xlib ffmpeg \
            libayatana-appindicator
        echo ">> gtk4-layer-shell (solo hace falta en Hyprland/Sway)..."
        if ! pacman -Qi gtk4-layer-shell &>/dev/null; then
            if command -v yay &>/dev/null; then
                yay -S --needed --noconfirm gtk4-layer-shell
            else
                sudo pacman -S --needed --noconfirm gtk4-layer-shell || {
                    echo "!! No pude instalar gtk4-layer-shell automáticamente."
                    echo "   Solo hace falta en Hyprland/Sway; instálalo desde"
                    echo "   el AUR si usas uno de esos: yay -S gtk4-layer-shell"
                }
            fi
        fi
        pacman -Qi libwnck3 &>/dev/null || sudo pacman -S --needed --noconfirm libwnck3 || true
        ;;
    apt)
        sudo apt update
        sudo apt install -y python3 python3-gi gir1.2-gtk-4.0 python3-pip \
            python3-pil python3-xlib ffmpeg gir1.2-ayatanaappindicator3-0.1 \
            gir1.2-wnck-3.0
        ;;
    dnf)
        sudo dnf install -y python3 python3-gobject gtk4 python3-pillow \
            python3-xlib ffmpeg libappindicator-gtk3 libwnck3
        ;;
    zypper)
        sudo zypper install -y python3 python3-gobject gtk4 python3-Pillow \
            python3-xlib ffmpeg libwnck3
        ;;
esac

echo ">> Instalando AnimaLinux..."
pip install --user --break-system-packages .

echo ">> Instalando recorte de fondo con IA (rembg). Es la descarga más pesada..."
pip install --user --break-system-packages rembg onnxruntime || {
    echo "!! No se pudo instalar rembg. La app funciona igual, pero para"
    echo "   recorte con IA reinténtalo: pip install --user --break-system-packages rembg onnxruntime"
}


echo ">> Registrando AnimaLinux en el menú de aplicaciones..."
BINDIR="$(python3 -m site --user-base)/bin"
APP_BIN="$BINDIR/animalinux"
mkdir -p ~/.local/share/applications
# Generamos el .desktop con la RUTA ABSOLUTA para que el menú lo encuentre
# aunque ~/.local/bin no esté en el PATH del lanzador.
cat > ~/.local/share/applications/animalinux.desktop <<EOF
[Desktop Entry]
Type=Application
Name=AnimaLinux
Comment=Mascotas animadas en el escritorio
Exec=$APP_BIN --show
Icon=face-smile
Terminal=false
Categories=Utility;Graphics;
Keywords=mascota;animacion;shimeji;desktop pet;
StartupNotify=false
EOF
update-desktop-database ~/.local/share/applications 2>/dev/null || true

echo ""
echo ">> Listo."
echo "   Ya aparece como «AnimaLinux» en tu menú de apps (quizá tras refrescar el menú)."
echo "   Autostart en Hyprland:   exec-once = $APP_BIN --daemon"
echo "   Autostart en GNOME/Cinnamon/MATE/Xfce: añade $APP_BIN --daemon en"
echo "   tus apps de inicio (o usa el toggle «Iniciar al encender» de la app)."
echo ""
# Avisar si ~/.local/bin no está en el PATH (para usar 'animalinux' en la terminal)
case ":$PATH:" in
    *":$BINDIR:"*) : ;;
    *)
        echo "   NOTA: '$BINDIR' no está en tu PATH. Para usar 'animalinux' en la"
        echo "   terminal, añade a tu ~/.bashrc o ~/.zshrc:"
        echo "       export PATH=\"$BINDIR:\$PATH\""
        ;;
esac
echo ""
echo "   (Opcional) recorte de fondo con IA, como AnimaEngine:"
echo "   pip install --user --break-system-packages rembg onnxruntime"
echo ""
echo "   Si 'animalinux' no se encuentra, añade ~/.local/bin al PATH."
