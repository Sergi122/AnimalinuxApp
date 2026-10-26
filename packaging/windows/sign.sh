#!/usr/bin/env bash
# Firma AnimaWin.exe y el instalador con un certificado de firma de código
# (Authenticode) desde Linux, con osslsigncode. Así Windows SmartScreen deja
# de mostrar «editor desconocido» (con un certificado OV la reputación se gana
# con las descargas; con EV o con Azure Trusted Signing es inmediata).
#
#   ANIMAWIN_SIGN_PFX=/ruta/cert.pfx ANIMAWIN_SIGN_PASS=... \
#       packaging/windows/sign.sh build/AnimaWin-Setup-0.7.0.exe [más .exe]
#
# Sin certificado no hace nada (y lo dice): firmar con uno autofirmado NO
# quita el aviso de SmartScreen, solo cambia el mensaje.
set -euo pipefail
PFX=${ANIMAWIN_SIGN_PFX:-}
if [ -z "$PFX" ]; then
    echo "ANIMAWIN_SIGN_PFX no está definido: no se firma nada."
    echo "Opciones: certificado OV/EV de una CA (Sectigo, Certum Open Source…),"
    echo "Azure Trusted Signing o SignPath.io (gratis para proyectos de código abierto)."
    exit 0
fi
command -v osslsigncode >/dev/null || { echo "Falta osslsigncode (pacman -S osslsigncode)"; exit 1; }
TS=${ANIMAWIN_SIGN_TS:-http://timestamp.digicert.com}
for exe in "$@"; do
    out="${exe%.exe}.signed.exe"
    osslsigncode sign -pkcs12 "$PFX" ${ANIMAWIN_SIGN_PASS:+-pass "$ANIMAWIN_SIGN_PASS"} \
        -n "AnimaWin" -i "https://animalinux.web.app" -h sha256 -ts "$TS" \
        -in "$exe" -out "$out"
    mv "$out" "$exe"
    osslsigncode verify -in "$exe" | grep -E "Signature verification|Message digest" || true
    echo "firmado: $exe"
done
