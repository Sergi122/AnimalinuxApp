"""
Sistema de internacionalización — AnimaLinux
Idiomas: es · en · pt · fr · de · ja · zh
Auto-detecta el idioma del sistema; configurable desde la app.
"""
import locale as _locale
from pathlib import Path

# ── idiomas disponibles ────────────────────────────────────────────────────────
LANGUAGES = {
    "es": "Español",
    "en": "English",
    "pt": "Português",
    "fr": "Français",
    "de": "Deutsch",
    "ja": "日本語",
    "zh": "中文",
}

# ── cadenas traducidas ─────────────────────────────────────────────────────────
_T: dict[str, dict[str, str]] = {

    # ── ventana principal ──────────────────────────────────────────────────────
    "app_title":            {"es":"AnimaLinux","en":"AnimaLinux","pt":"AnimaLinux","fr":"AnimaLinux","de":"AnimaLinux","ja":"AnimaLinux","zh":"AnimaLinux"},
    "tab_normal":           {"es":"🎬 Normal (GIF)","en":"🎬 Normal (GIF)","pt":"🎬 Normal (GIF)","fr":"🎬 Normal (GIF)","de":"🎬 Normal (GIF)","ja":"🎬 通常 (GIF)","zh":"🎬 普通 (GIF)"},
    "tab_vida":             {"es":"✨ Con vida","en":"✨ With life","pt":"✨ Com vida","fr":"✨ Avec vie","de":"✨ Mit Leben","ja":"✨ 生き生き","zh":"✨ 有生命"},
    "new_normal":           {"es":"➕  Nueva animación GIF","en":"➕  New GIF animation","pt":"➕  Nova animação GIF","fr":"➕  Nouvelle animation GIF","de":"➕  Neue GIF-Animation","ja":"➕  新しいGIFアニメ","zh":"➕  新建GIF动画"},
    "new_vida":             {"es":"➕  Nueva animación con vida","en":"➕  New living animation","pt":"➕  Nova animação com vida","fr":"➕  Nouvelle animation vivante","de":"➕  Neue lebendige Animation","ja":"➕  新しい生きアニメ","zh":"➕  新建生动动画"},
    "import_done":          {"es":"Importar ya hecho:","en":"Import existing:","pt":"Importar já feito:","fr":"Importer existant :","de":"Vorhandenes importieren:","ja":"既存をインポート:","zh":"导入已有文件:"},
    "import_folder":        {"es":"Importar ya hecha:","en":"Import existing:","pt":"Importar já feita:","fr":"Importer existante :","de":"Vorhandene importieren:","ja":"既存をインポート:","zh":"导入已有:"},
    "how_create":           {"es":"¿Cómo quieres crear tu animación?","en":"How do you want to create your animation?","pt":"Como quer criar sua animação?","fr":"Comment créer votre animation ?","de":"Wie möchten Sie Ihre Animation erstellen?","ja":"アニメをどのように作りますか?","zh":"如何创建动画?"},
    "how_create_vida":      {"es":"¿Cómo crear tu animación con vida?","en":"How to create your living animation?","pt":"Como criar sua animação com vida?","fr":"Comment créer votre animation vivante ?","de":"Wie eine lebendige Animation erstellen?","ja":"生きアニメをどう作りますか?","zh":"如何创建生动动画?"},
    "btn_import":           {"es":"📥 Importar","en":"📥 Import","pt":"📥 Importar","fr":"📥 Importer","de":"📥 Importieren","ja":"📥 インポート","zh":"📥 导入"},
    "btn_import_desc":      {"es":"gif · mp4 · imagen","en":"gif · mp4 · image","pt":"gif · mp4 · imagem","fr":"gif · mp4 · image","de":"gif · mp4 · Bild","ja":"gif · mp4 · 画像","zh":"gif · mp4 · 图片"},
    "btn_pixel":            {"es":"🎨 Píxel art","en":"🎨 Pixel art","pt":"🎨 Arte em pixels","fr":"🎨 Pixel art","de":"🎨 Pixel-Art","ja":"🎨 ピクセルアート","zh":"🎨 像素艺术"},
    "btn_pixel_desc":       {"es":"lienzo por celdas\nestilo retro","en":"cell-by-cell canvas\nretro style","pt":"tela em células\nestilo retrô","fr":"canevas cellule par cellule\nstyle rétro","de":"Zellenleinwand\nRetro-Stil","ja":"マス目キャンバス\nレトロスタイル","zh":"像素格画布\n复古风格"},
    "btn_paint":            {"es":"🖌️ Dibujo libre","en":"🖌️ Free drawing","pt":"🖌️ Desenho livre","fr":"🖌️ Dessin libre","de":"🖌️ Freies Zeichnen","ja":"🖌️ 自由描画","zh":"🖌️ 自由绘画"},
    "btn_paint_desc":       {"es":"pincel suave\nalta resolución","en":"smooth brush\nhigh resolution","pt":"pincel suave\nalta resolução","fr":"pinceau doux\nhaute résolution","de":"weicher Pinsel\nhohe Auflösung","ja":"なめらかブラシ\n高解像度","zh":"柔滑笔刷\n高分辨率"},
    "btn_continue":         {"es":"📁 Continuar proyecto","en":"📁 Continue project","pt":"📁 Continuar projeto","fr":"📁 Continuer le projet","de":"📁 Projekt fortsetzen","ja":"📁 プロジェクト再開","zh":"📁 继续项目"},
    "btn_continue_desc":    {"es":"retomar un .alproj\nguardado antes","en":"resume a saved\n.alproj file","pt":"retomar um .alproj\nsalvo antes","fr":"reprendre un .alproj\nsauvegardé","de":"gespeichertes .alproj\nfortsetzen","ja":"保存済み .alproj\nを再開","zh":"继续保存的\n.alproj文件"},
    "bg_method":            {"es":"Quitar fondo al importar:","en":"Background removal:","pt":"Remover fundo ao importar:","fr":"Supprimer le fond à l'import :","de":"Hintergrund beim Import:","ja":"インポート時の背景削除:","zh":"导入时去除背景:"},
    "pack_btn":             {"es":"Pack (.alpack)","en":"Pack (.alpack)","pt":"Pack (.alpack)","fr":"Pack (.alpack)","de":"Pack (.alpack)","ja":"パック(.alpack)","zh":"包(.alpack)"},
    "spritesheet":          {"es":"Spritesheet","en":"Spritesheet","pt":"Spritesheet","fr":"Spritesheet","de":"Spritesheet","ja":"スプライトシート","zh":"精灵表"},
    "cols":                 {"es":"cols:","en":"cols:","pt":"colunas:","fr":"col :","de":"Spalten:","ja":"列:","zh":"列:"},
    "folder_mascot":        {"es":"Carpeta de mascota","en":"Mascot folder","pt":"Pasta de mascote","fr":"Dossier de mascotte","de":"Maskottchenordner","ja":"マスコットフォルダ","zh":"吉祥物文件夹"},
    "how_add_pose":         {"es":"¿Cómo crear poses?","en":"How to create poses?","pt":"Como criar poses?","fr":"Comment créer des poses ?","de":"Wie Posen erstellen?","ja":"ポーズの作り方?","zh":"如何创建动作?"},
    "vida_help":            {"es":"❓ ¿Cómo crear poses?","en":"❓ How to create poses?","pt":"❓ Como criar poses?","fr":"❓ Comment créer des poses ?","de":"❓ Wie Posen erstellen?","ja":"❓ ポーズの作り方?","zh":"❓ 如何创建动作?"},
    "fps_label":            {"es":"FPS:","en":"FPS:","pt":"FPS:","fr":"FPS :","de":"FPS:","ja":"FPS:","zh":"帧率:"},
    "show_desktop":         {"es":"Mostrar en escritorio","en":"Show on desktop","pt":"Mostrar na área de trabalho","fr":"Afficher sur le bureau","de":"Auf dem Desktop anzeigen","ja":"デスクトップに表示","zh":"在桌面显示"},
    "edit_pixel":           {"es":"🎨 Editar","en":"🎨 Edit","pt":"🎨 Editar","fr":"🎨 Modifier","de":"🎨 Bearbeiten","ja":"🎨 編集","zh":"🎨 编辑"},
    "edit_paint":           {"es":"🖌️ Editar","en":"🖌️ Edit","pt":"🖌️ Editar","fr":"🖌️ Modifier","de":"🖌️ Bearbeiten","ja":"🖌️ 編集","zh":"🖌️ 编辑"},
    "to_life":              {"es":"→ Con vida","en":"→ Add life","pt":"→ Com vida","fr":"→ Avec vie","de":"→ Mit Leben","ja":"→ 生命を追加","zh":"→ 添加生命"},
    "export":               {"es":"📦 Exportar","en":"📦 Export","pt":"📦 Exportar","fr":"📦 Exporter","de":"📦 Exportieren","ja":"📦 エクスポート","zh":"📦 导出"},
    "delete":               {"es":"🗑 Eliminar","en":"🗑 Delete","pt":"🗑 Eliminar","fr":"🗑 Supprimer","de":"🗑 Löschen","ja":"🗑 削除","zh":"🗑 删除"},
    "add_pose":             {"es":"Añadir pose:","en":"Add pose:","pt":"Adicionar pose:","fr":"Ajouter une pose :","de":"Pose hinzufügen:","ja":"ポーズを追加:","zh":"添加动作:"},
    "gen_poses":            {"es":"⚙️ Generar poses","en":"⚙️ Generate poses","pt":"⚙️ Gerar poses","fr":"⚙️ Générer des poses","de":"⚙️ Posen generieren","ja":"⚙️ ポーズ生成","zh":"⚙️ 生成动作"},
    "poses_label":          {"es":"Poses: ","en":"Poses: ","pt":"Poses: ","fr":"Poses : ","de":"Posen: ","ja":"ポーズ: ","zh":"动作: "},
    "no_anims":             {"es":"Sin animaciones todavía — crea la primera arriba.","en":"No animations yet — create the first one above.","pt":"Sem animações ainda — crie a primeira acima.","fr":"Aucune animation — créez la première ci-dessus.","de":"Keine Animationen — erstellen Sie die erste oben.","ja":"アニメなし — 上から最初のを作成してください。","zh":"还没有动画 — 在上方创建第一个。"},
    "processing":           {"es":"Procesando…","en":"Processing…","pt":"Processando…","fr":"Traitement…","de":"Verarbeitung…","ja":"処理中…","zh":"处理中…"},
    "error":                {"es":"Error: ","en":"Error: ","pt":"Erro: ","fr":"Erreur : ","de":"Fehler: ","ja":"エラー: ","zh":"错误: "},

    # ── proyectos ──────────────────────────────────────────────────────────────
    "projects_title":       {"es":"Continuar proyecto","en":"Continue project","pt":"Continuar projeto","fr":"Continuer le projet","de":"Projekt fortsetzen","ja":"プロジェクト再開","zh":"继续项目"},
    "projects_empty":       {"es":"No hay proyectos guardados.\nGuarda uno con Ctrl+Shift+S en el editor.","en":"No saved projects found.\nSave one with Ctrl+Shift+S in the editor.","pt":"Nenhum projeto salvo.\nSalve um com Ctrl+Shift+S no editor.","fr":"Aucun projet sauvegardé.\nSauvegardez avec Ctrl+Maj+S dans l'éditeur.","de":"Keine gespeicherten Projekte.\nSpeichern Sie mit Strg+Umschalt+S im Editor.","ja":"保存済みプロジェクトなし。\nエディタでCtrl+Shift+Sで保存。","zh":"没有已保存的项目。\n在编辑器中按Ctrl+Shift+S保存。"},
    "projects_open":        {"es":"Abrir","en":"Open","pt":"Abrir","fr":"Ouvrir","de":"Öffnen","ja":"開く","zh":"打开"},
    "projects_folder":      {"es":"📂 Ver carpeta","en":"📂 Open folder","pt":"📂 Ver pasta","fr":"📂 Voir le dossier","de":"📂 Ordner öffnen","ja":"📂 フォルダを開く","zh":"📂 打开文件夹"},
    "projects_modified":    {"es":"Modificado:","en":"Modified:","pt":"Modificado:","fr":"Modifié :","de":"Geändert:","ja":"変更日:","zh":"修改时间:"},

    # ── configuración / idioma ─────────────────────────────────────────────────
    "settings_title":       {"es":"⚙️ Configuración","en":"⚙️ Settings","pt":"⚙️ Configurações","fr":"⚙️ Paramètres","de":"⚙️ Einstellungen","ja":"⚙️ 設定","zh":"⚙️ 设置"},
    "lang_label":           {"es":"Idioma / Language:","en":"Language:","pt":"Idioma:","fr":"Langue :","de":"Sprache:","ja":"言語:","zh":"语言:"},
    "lang_restart":         {"es":"(El cambio se aplica al reabrir las ventanas)","en":"(Change applies when reopening windows)","pt":"(A mudança é aplicada ao reabrir as janelas)","fr":"(Le changement s'applique à la réouverture des fenêtres)","de":"(Änderung gilt nach erneutem Öffnen der Fenster)","ja":"(変更はウィンドウを再度開くと適用されます)","zh":"(更改在重新打开窗口后生效)"},
    "autostart_label":      {"es":"Iniciar al encender el sistema","en":"Start when the system boots","pt":"Iniciar ao ligar o sistema","fr":"Démarrer au lancement du système","de":"Beim Systemstart starten","ja":"システム起動時に開始","zh":"开机时启动"},
    "autostart_hint":       {"es":"(Se aplica al próximo inicio de sesión)","en":"(Applies at the next login)","pt":"(Aplica-se no próximo login)","fr":"(S'applique à la prochaine connexion)","de":"(Gilt ab der nächsten Anmeldung)","ja":"(次回のログインから適用)","zh":"(将在下次登录时生效)"},
    "ok":                   {"es":"✓ Aceptar","en":"✓ OK","pt":"✓ OK","fr":"✓ OK","de":"✓ OK","ja":"✓ OK","zh":"✓ 确定"},
    "cancel":               {"es":"Cancelar","en":"Cancel","pt":"Cancelar","fr":"Annuler","de":"Abbrechen","ja":"キャンセル","zh":"取消"},

    # ── editor de pintura ──────────────────────────────────────────────────────
    "paint_title":          {"es":"Editor de Pintura — AnimaLinux","en":"Paint Editor — AnimaLinux","pt":"Editor de Pintura — AnimaLinux","fr":"Éditeur de peinture — AnimaLinux","de":"Malen-Editor — AnimaLinux","ja":"ペイントエディタ — AnimaLinux","zh":"绘画编辑器 — AnimaLinux"},
    "save_pose_btn":        {"es":"💾 Guardar pose","en":"💾 Save pose","pt":"💾 Salvar pose","fr":"💾 Sauvegarder la pose","de":"💾 Pose speichern","ja":"💾 ポーズを保存","zh":"💾 保存动作"},
    "pose_label":           {"es":"Pose:","en":"Pose:","pt":"Pose:","fr":"Pose :","de":"Pose:","ja":"ポーズ:","zh":"动作:"},
    "name_label":           {"es":"Nombre:","en":"Name:","pt":"Nome:","fr":"Nom :","de":"Name:","ja":"名前:","zh":"名称:"},
    "layers_label":         {"es":"Capas","en":"Layers","pt":"Camadas","fr":"Calques","de":"Ebenen","ja":"レイヤー","zh":"图层"},
    "frames_label":         {"es":"Frames","en":"Frames","pt":"Quadros","fr":"Images","de":"Bilder","ja":"フレーム","zh":"帧"},
    "tools_label":          {"es":"Herramientas","en":"Tools","pt":"Ferramentas","fr":"Outils","de":"Werkzeuge","ja":"ツール","zh":"工具"},
    "colors_label":         {"es":"Colores","en":"Colors","pt":"Cores","fr":"Couleurs","de":"Farben","ja":"カラー","zh":"颜色"},
    "recent_label":         {"es":"Recientes","en":"Recent","pt":"Recentes","fr":"Récents","de":"Zuletzt","ja":"最近","zh":"最近"},
    "brush_label":          {"es":"Pincel:","en":"Brush:","pt":"Pincel:","fr":"Pinceau :","de":"Pinsel:","ja":"ブラシ:","zh":"笔刷:"},
    "radius_label":         {"es":"Radio:","en":"Radius:","pt":"Raio:","fr":"Rayon :","de":"Radius:","ja":"半径:","zh":"半径:"},
    "softness_label":       {"es":"Suavidad:","en":"Softness:","pt":"Suavidade:","fr":"Douceur :","de":"Weichheit:","ja":"柔らかさ:","zh":"柔和度:"},
    "opacity_label":        {"es":"Opacidad:","en":"Opacity:","pt":"Opacidade:","fr":"Opacité :","de":"Opazität:","ja":"不透明度:","zh":"不透明度:"},
    "wand_tol":             {"es":"Varita tol.:","en":"Wand tol.:","pt":"Varinha tol.:","fr":"Tol. baguette :","de":"Zauberstab-Tol.:","ja":"魔法棒許容度:","zh":"魔棒容差:"},
    "save_project_btn":     {"es":"💾 Proyecto","en":"💾 Project","pt":"💾 Projeto","fr":"💾 Projet","de":"💾 Projekt","ja":"💾 プロジェクト","zh":"💾 项目"},
    "open_project_btn":     {"es":"📂 Proyecto","en":"📂 Project","pt":"📂 Projeto","fr":"📂 Projet","de":"📂 Projekt","ja":"📂 プロジェクト","zh":"📂 项目"},

    # ── editor de píxeles ─────────────────────────────────────────────────────
    "pixel_title":          {"es":"Editor de Píxeles — AnimaLinux","en":"Pixel Editor — AnimaLinux","pt":"Editor de Pixels — AnimaLinux","fr":"Éditeur de pixels — AnimaLinux","de":"Pixel-Editor — AnimaLinux","ja":"ピクセルエディタ — AnimaLinux","zh":"像素编辑器 — AnimaLinux"},
}

# ── estado del idioma activo ───────────────────────────────────────────────────
_lang: str = "es"


def _detect_system_lang() -> str:
    """Detecta el idioma del sistema y lo mapea a uno soportado."""
    try:
        import locale as _loc
        loc = _loc.getlocale()[0] or ""
        code = loc[:2].lower()
        return code if code in LANGUAGES else "es"
    except Exception:
        return "es"


def init():
    """Inicializa el idioma desde settings o auto-detección."""
    global _lang
    from . import settings as _s
    stored = _s.get("language", None)
    if stored and stored in LANGUAGES:
        _lang = stored
    else:
        detected = _detect_system_lang()
        _lang = detected
        _s.set_val("language", detected)


def set_language(code: str):
    """Cambia el idioma activo y lo persiste."""
    global _lang
    if code in LANGUAGES:
        _lang = code
        from . import settings as _s
        _s.set_val("language", code)


def get_language() -> str:
    return _lang


def t(key: str, **kwargs) -> str:
    """Devuelve la cadena traducida al idioma activo."""
    entry = _T.get(key)
    if entry is None:
        return key
    text = entry.get(_lang) or entry.get("es") or key
    return text.format(**kwargs) if kwargs else text
