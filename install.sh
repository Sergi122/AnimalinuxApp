#!/usr/bin/env bash
# Instalador de AnimaLinux para Arch Linux + Hyprland
set -e

echo ">> Instalando dependencias del sistema..."
sudo pacman -S --needed --noconfirm \
    gtk4 python-gobject python-pillow ffmpeg libayatana-appindicator

echo ">> gtk4-layer-shell (necesario para el overlay)..."
if ! pacman -Qi gtk4-layer-shell &>/dev/null; then
    if command -v yay &>/dev/null; then
        yay -S --needed --noconfirm gtk4-layer-shell
    else
        sudo pacman -S --needed --noconfirm gtk4-layer-shell || {
            echo "!! No pude instalar gtk4-layer-shell automáticamente."
            echo "   Instálalo desde el AUR: yay -S gtk4-layer-shell"
        }
    fi
fi

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
