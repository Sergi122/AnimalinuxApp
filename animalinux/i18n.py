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
    "tab_normal":           {"es":"Normal (GIF)","en":"Normal (GIF)","pt":"Normal (GIF)","fr":"Normal (GIF)","de":"Normal (GIF)","ja":"通常 (GIF)","zh":"普通 (GIF)"},
    "tab_vida":             {"es":"Con vida","en":"With life","pt":"Com vida","fr":"Avec vie","de":"Mit Leben","ja":"生き生き","zh":"有生命"},
    "new_normal":           {"es":"Nueva animación GIF","en":"New GIF animation","pt":"Nova animação GIF","fr":"Nouvelle animation GIF","de":"Neue GIF-Animation","ja":"新しいGIFアニメ","zh":"新建GIF动画"},
    "new_vida":             {"es":"Nueva animación con vida","en":"New living animation","pt":"Nova animação com vida","fr":"Nouvelle animation vivante","de":"Neue lebendige Animation","ja":"新しい生きアニメ","zh":"新建生动动画"},
    "import_done":          {"es":"Importar ya hecho:","en":"Import existing:","pt":"Importar já feito:","fr":"Importer existant :","de":"Vorhandenes importieren:","ja":"既存をインポート:","zh":"导入已有文件:"},
    "import_folder":        {"es":"Importar ya hecha:","en":"Import existing:","pt":"Importar já feita:","fr":"Importer existante :","de":"Vorhandene importieren:","ja":"既存をインポート:","zh":"导入已有:"},
    "how_create":           {"es":"¿Cómo quieres crear tu animación?","en":"How do you want to create your animation?","pt":"Como quer criar sua animação?","fr":"Comment créer votre animation ?","de":"Wie möchten Sie Ihre Animation erstellen?","ja":"アニメをどのように作りますか?","zh":"如何创建动画?"},
    "how_create_vida":      {"es":"¿Cómo crear tu animación con vida?","en":"How to create your living animation?","pt":"Como criar sua animação com vida?","fr":"Comment créer votre animation vivante ?","de":"Wie eine lebendige Animation erstellen?","ja":"生きアニメをどう作りますか?","zh":"如何创建生动动画?"},
    "btn_import":           {"es":"Importar","en":"Import","pt":"Importar","fr":"Importer","de":"Importieren","ja":"インポート","zh":"导入"},
    "btn_import_desc":      {"es":"gif · mp4 · imagen","en":"gif · mp4 · image","pt":"gif · mp4 · imagem","fr":"gif · mp4 · image","de":"gif · mp4 · Bild","ja":"gif · mp4 · 画像","zh":"gif · mp4 · 图片"},
    "btn_import_desc_vida": {"es":"pack .alpack\nexportado desde AnimaLinux","en":".alpack pack\nexported from AnimaLinux","pt":"pacote .alpack\nexportado do AnimaLinux","fr":"pack .alpack\nexporté depuis AnimaLinux","de":".alpack-Paket\naus AnimaLinux exportiert","ja":"AnimaLinuxから\nエクスポートした.alpackパック","zh":"从AnimaLinux\n导出的.alpack包"},
    "btn_pixel":            {"es":"Píxel art","en":"Pixel art","pt":"Arte em pixels","fr":"Pixel art","de":"Pixel-Art","ja":"ピクセルアート","zh":"像素艺术"},
    "btn_pixel_desc":       {"es":"lienzo por celdas\nestilo retro","en":"cell-by-cell canvas\nretro style","pt":"tela em células\nestilo retrô","fr":"canevas cellule par cellule\nstyle rétro","de":"Zellenleinwand\nRetro-Stil","ja":"マス目キャンバス\nレトロスタイル","zh":"像素格画布\n复古风格"},
    "btn_paint":            {"es":"Dibujo libre","en":"Free drawing","pt":"Desenho livre","fr":"Dessin libre","de":"Freies Zeichnen","ja":"自由描画","zh":"自由绘画"},
    "btn_paint_desc":       {"es":"pincel suave\nalta resolución","en":"smooth brush\nhigh resolution","pt":"pincel suave\nalta resolução","fr":"pinceau doux\nhaute résolution","de":"weicher Pinsel\nhohe Auflösung","ja":"なめらかブラシ\n高解像度","zh":"柔滑笔刷\n高分辨率"},
    "btn_continue":         {"es":"Continuar proyecto","en":"Continue project","pt":"Continuar projeto","fr":"Continuer le projet","de":"Projekt fortsetzen","ja":"プロジェクト再開","zh":"继续项目"},
    "btn_continue_desc":    {"es":"retomar un .alproj\nguardado antes","en":"resume a saved\n.alproj file","pt":"retomar um .alproj\nsalvo antes","fr":"reprendre un .alproj\nsauvegardé","de":"gespeichertes .alproj\nfortsetzen","ja":"保存済み .alproj\nを再開","zh":"继续保存的\n.alproj文件"},
    "bg_method":            {"es":"Quitar fondo al importar:","en":"Background removal:","pt":"Remover fundo ao importar:","fr":"Supprimer le fond à l'import :","de":"Hintergrund beim Import:","ja":"インポート時の背景削除:","zh":"导入时去除背景:"},
    "bg_ai":                {"es":"IA (recorte limpio)","en":"AI (clean cutout)","pt":"IA (recorte limpo)","fr":"IA (découpe nette)","de":"KI (sauberer Ausschnitt)","ja":"AI(きれいな切り抜き)","zh":"AI(干净抠图)"},
    "bg_chroma":            {"es":"Color de fondo (rápido)","en":"Background color (fast)","pt":"Cor de fundo (rápido)","fr":"Couleur de fond (rapide)","de":"Hintergrundfarbe (schnell)","ja":"背景色(高速)","zh":"背景色(快速)"},
    "bg_none":              {"es":"Ninguno (ya transparente)","en":"None (already transparent)","pt":"Nenhum (já transparente)","fr":"Aucun (déjà transparent)","de":"Keine (bereits transparent)","ja":"なし(既に透明)","zh":"无(已透明)"},
    "import_label":         {"es":"Importar:","en":"Import:","pt":"Importar:","fr":"Importer :","de":"Importieren:","ja":"インポート:","zh":"导入:"},
    "import_gif":           {"es":"GIF / WebP / APNG","en":"GIF / WebP / APNG","pt":"GIF / WebP / APNG","fr":"GIF / WebP / APNG","de":"GIF / WebP / APNG","ja":"GIF / WebP / APNG","zh":"GIF / WebP / APNG"},
    "import_video":         {"es":"MP4 / WebM / MOV","en":"MP4 / WebM / MOV","pt":"MP4 / WebM / MOV","fr":"MP4 / WebM / MOV","de":"MP4 / WebM / MOV","ja":"MP4 / WebM / MOV","zh":"MP4 / WebM / MOV"},
    "spritesheet":          {"es":"Spritesheet","en":"Spritesheet","pt":"Spritesheet","fr":"Spritesheet","de":"Spritesheet","ja":"スプライトシート","zh":"精灵表"},
    "cols":                 {"es":"cols:","en":"cols:","pt":"colunas:","fr":"col :","de":"Spalten:","ja":"列:","zh":"列:"},
    "folder_mascot":        {"es":"Carpeta de mascota","en":"Mascot folder","pt":"Pasta de mascote","fr":"Dossier de mascotte","de":"Maskottchenordner","ja":"マスコットフォルダ","zh":"吉祥物文件夹"},
    "vida_help":            {"es":"¿Cómo crear poses?","en":"How to create poses?","pt":"Como criar poses?","fr":"Comment créer des poses ?","de":"Wie Posen erstellen?","ja":"ポーズの作り方?","zh":"如何创建动作?"},
    "fps_label":            {"es":"FPS:","en":"FPS:","pt":"FPS:","fr":"FPS :","de":"FPS:","ja":"FPS:","zh":"帧率:"},
    "show_desktop":         {"es":"Mostrar en escritorio","en":"Show on desktop","pt":"Mostrar na área de trabalho","fr":"Afficher sur le bureau","de":"Auf dem Desktop anzeigen","ja":"デスクトップに表示","zh":"在桌面显示"},
    "edit_pixel":           {"es":"Editar","en":"Edit","pt":"Editar","fr":"Modifier","de":"Bearbeiten","ja":"編集","zh":"编辑"},
    "edit_paint":           {"es":"Editar","en":"Edit","pt":"Editar","fr":"Modifier","de":"Bearbeiten","ja":"編集","zh":"编辑"},
    "to_life":              {"es":"→ Con vida","en":"→ Add life","pt":"→ Com vida","fr":"→ Avec vie","de":"→ Mit Leben","ja":"→ 生命を追加","zh":"→ 添加生命"},
    "export":               {"es":"Exportar","en":"Export","pt":"Exportar","fr":"Exporter","de":"Exportieren","ja":"エクスポート","zh":"导出"},
    "delete":               {"es":"Eliminar","en":"Delete","pt":"Eliminar","fr":"Supprimer","de":"Löschen","ja":"削除","zh":"删除"},
    "add_pose":             {"es":"Añadir pose:","en":"Add pose:","pt":"Adicionar pose:","fr":"Ajouter une pose :","de":"Pose hinzufügen:","ja":"ポーズを追加:","zh":"添加动作:"},
    "add_pose_pixel":       {"es":"Píxeles","en":"Pixels","pt":"Pixels","fr":"Pixels","de":"Pixel","ja":"ピクセル","zh":"像素"},
    "add_pose_paint":       {"es":"Libre","en":"Free","pt":"Livre","fr":"Libre","de":"Frei","ja":"自由","zh":"自由"},
    "active_poses":         {"es":"Poses activas:","en":"Active poses:","pt":"Poses ativas:","fr":"Poses actives :","de":"Aktive Posen:","ja":"有効なポーズ:","zh":"启用的动作:"},
    "active_poses_hint":    {"es":"Solo las poses obligatorias — dibujá o importá más (greet, kiss, angry, sleep, grab…)","en":"Only the mandatory poses — draw or import more (greet, kiss, angry, sleep, grab…)","pt":"Só as poses obrigatórias — desenhe ou importe mais (greet, kiss, angry, sleep, grab…)","fr":"Seulement les poses obligatoires — dessinez ou importez-en d'autres (greet, kiss, angry, sleep, grab…)","de":"Nur die Pflicht-Posen — mehr zeichnen oder importieren (greet, kiss, angry, sleep, grab…)","ja":"必須ポーズのみ — もっと描くかインポートしてください(greet, kiss, angry, sleep, grab…)","zh":"仅有必需动作 — 绘制或导入更多(greet、kiss、angry、sleep、grab…)"},
    "guided_editor_title":  {"es":"¿Con qué editor crear las poses?","en":"Which editor do you want to use for the poses?","pt":"Com qual editor criar as poses?","fr":"Avec quel éditeur créer les poses ?","de":"Mit welchem Editor Posen erstellen?","ja":"どのエディタでポーズを作りますか?","zh":"用哪个编辑器创建动作?"},
    "guided_editor_desc":   {"es":"Elige el editor para crear las poses de vida:","en":"Choose the editor to create the living poses:","pt":"Escolha o editor para criar as poses:","fr":"Choisissez l'éditeur pour créer les poses :","de":"Wähle den Editor für die Posen:","ja":"ポーズを作るエディタを選んでください:","zh":"选择用于创建动作的编辑器:"},
    "mascot_imported":      {"es":"Mascota importada","en":"Mascot imported","pt":"Mascote importado","fr":"Mascotte importée","de":"Maskottchen importiert","ja":"マスコットをインポートしました","zh":"已导入吉祥物"},
    "guide_title_poses":    {"es":"POSES NECESARIAS","en":"REQUIRED POSES","pt":"POSES NECESSÁRIAS","fr":"POSES NÉCESSAIRES","de":"NÖTIGE POSEN","ja":"必要なポーズ","zh":"所需动作"},
    "guide_intro":          {"es":"Una animación «con vida» se compone de varias poses. La app elige la correcta según lo que hace la mascota en pantalla.","en":"A \"living\" animation is made of several poses. The app picks the right one depending on what the mascot is doing on screen.","pt":"Uma animação \"com vida\" é composta por várias poses. O app escolhe a correta conforme o que a mascote faz na tela.","fr":"Une animation « vivante » se compose de plusieurs poses. L'appli choisit la bonne selon ce que fait la mascotte à l'écran.","de":"Eine „lebendige“ Animation besteht aus mehreren Posen. Die App wählt je nach Aktion des Maskottchens die richtige aus.","ja":"「生きている」アニメーションは複数のポーズで構成されます。画面上のマスコットの動作に応じてアプリが正しいポーズを選びます。","zh":"一个「生动」动画由多个动作组成。应用会根据吉祥物在屏幕上的行为选择合适的动作。"},
    "guide_pose_default":   {"es":"default — Pose base / parada","en":"default — Base pose / standing","pt":"default — Pose base / parado","fr":"default — Pose de base / immobile","de":"default — Grundpose / stehend","ja":"default — 基本ポーズ・静止","zh":"default — 基础姿势/静止"},
    "guide_pose_idle":      {"es":"idle — Respirar / quieta","en":"idle — Breathing / still","pt":"idle — Respirando / parado","fr":"idle — Respiration / immobile","de":"idle — Atmen / ruhig","ja":"idle — 呼吸・静止中","zh":"idle — 呼吸/静止"},
    "guide_pose_walk":      {"es":"walk — Caminar","en":"walk — Walking","pt":"walk — Caminhando","fr":"walk — Marche","de":"walk — Gehen","ja":"walk — 歩く","zh":"walk — 行走"},
    "guide_pose_greet":     {"es":"greet — Saludar (al acercarse a otra mascota, o al usuario)","en":"greet — Greeting (approaching another mascot, or the user)","pt":"greet — Cumprimentar (ao se aproximar de outra mascote, ou do usuário)","fr":"greet — Saluer (en s'approchant d'une autre mascotte, ou de l'utilisateur)","de":"greet — Grüßen (bei Annäherung an ein anderes Maskottchen oder den Nutzer)","ja":"greet — 挨拶(他のマスコットやユーザーに近づいた時)","zh":"greet — 打招呼(靠近其他吉祥物或用户时)"},
    "guide_pose_kiss":      {"es":"kiss — Le manda un beso al usuario al azar, en vez de «greet», cuando el cursor pasa encima","en":"kiss — Randomly blows a kiss to the user instead of «greet», when the cursor hovers over it","pt":"kiss — Manda um beijo ao usuário aleatoriamente, em vez de «greet», quando o cursor passa por cima","fr":"kiss — Envoie parfois un baiser à l'utilisateur au lieu de « greet », quand le curseur passe dessus","de":"kiss — Schickt dem Nutzer manchmal statt „greet“ einen Kuss zu, wenn der Cursor darüberfährt","ja":"kiss — カーソルが乗った時、稀に「greet」の代わりにユーザーにキスを送る","zh":"kiss — 光标悬停时,有时会代替「greet」给用户送上飞吻"},
    "guide_pose_jump":      {"es":"jump — Saltar (squash/stretch)","en":"jump — Jumping (squash/stretch)","pt":"jump — Pular (squash/stretch)","fr":"jump — Sauter (squash/stretch)","de":"jump — Springen (Squash/Stretch)","ja":"jump — ジャンプ(スクワッシュ・ストレッチ)","zh":"jump — 跳跃(挤压/拉伸)"},
    "guide_pose_angry":     {"es":"angry — Enojo / voltear","en":"angry — Anger / turning away","pt":"angry — Raiva / virar","fr":"angry — Colère / se retourner","de":"angry — Wut / Abwenden","ja":"angry — 怒り・向き直り","zh":"angry — 生气/转身"},
    "guide_pose_grab":      {"es":"grab — Agarrar el ratón (4 clicks)","en":"grab — Grabbing the mouse (4 clicks)","pt":"grab — Agarrar o mouse (4 cliques)","fr":"grab — Attraper la souris (4 clics)","de":"grab — Die Maus greifen (4 Klicks)","ja":"grab — マウスをつかむ(4回クリック)","zh":"grab — 抓住鼠标(点击4次)"},
    "guide_only_default":   {"es":"Solo «default» es obligatoria. Las demás son opcionales — la app usa «default» si faltan.","en":"Only «default» is mandatory. The rest are optional — the app falls back to «default» if they're missing.","pt":"Só «default» é obrigatória. As demais são opcionais — o app usa «default» se faltarem.","fr":"Seule « default » est obligatoire. Les autres sont facultatives — l'appli utilise « default » si elles manquent.","de":"Nur „default“ ist Pflicht. Die anderen sind optional — die App verwendet „default“, wenn sie fehlen.","ja":"「default」のみ必須です。他は任意 — 無ければアプリは「default」を使います。","zh":"只有「default」是必需的。其余都是可选的——缺少时应用会使用「default」。"},
    "guide_title_create":   {"es":"CÓMO CREAR LAS POSES","en":"HOW TO CREATE POSES","pt":"COMO CRIAR AS POSES","fr":"COMMENT CRÉER LES POSES","de":"WIE MAN POSEN ERSTELLT","ja":"ポーズの作り方","zh":"如何创建动作"},
    "guide_create_intro":   {"es":"Las poses NO se generan solas: hay que dibujarlas (o traerlas ya hechas en un pack .alpack). Una imagen sola, sin dibujar nada, solo da la pose «default» — la mascota queda quieta en modo Vida hasta que le sumes poses.","en":"Poses are NOT generated automatically: you have to draw them (or bring them ready-made in an .alpack pack). A single image alone, with nothing drawn, only gives the «default» pose — the mascot stays still in Life mode until you add poses.","pt":"As poses NÃO são geradas sozinhas: é preciso desenhá-las (ou trazê-las prontas num pacote .alpack). Uma imagem sozinha, sem desenhar nada, só dá a pose «default» — a mascote fica parada no modo Vida até você adicionar poses.","fr":"Les poses ne se génèrent PAS toutes seules : il faut les dessiner (ou les importer déjà faites dans un pack .alpack). Une seule image, sans rien dessiner, ne donne que la pose « default » — la mascotte reste immobile en mode Vie tant que vous n'ajoutez pas de poses.","de":"Posen werden NICHT automatisch erzeugt: Man muss sie zeichnen (oder fertig in einem .alpack-Paket mitbringen). Ein einzelnes Bild ohne Zeichnung ergibt nur die Pose „default“ — das Maskottchen bleibt im Lebendig-Modus reglos, bis Posen hinzugefügt werden.","ja":"ポーズは自動生成されません。自分で描く(または.alpackパックとして持ち込む)必要があります。何も描かない1枚の画像だけでは「default」ポーズしか得られず、ポーズを追加するまでマスコットは生きているモードで静止したままです。","zh":"动作不会自动生成:必须手绘(或以.alpack包的形式导入现成的)。仅有一张图片、不绘制任何内容,只会得到「default」姿势——在添加更多动作之前,吉祥物在生动模式下会保持静止。"},
    "guide_steps":          {"es":"1. Pulsa «Nueva animación con vida»\n2. Elige dibujar (Píxeles/Libre), o importar un pack .alpack ya hecho\n3. En el editor, escribe el nombre de la pose en el campo inferior (ej: walk)\n4. Dibuja los frames de esa acción\n5. Pulsa «Guardar pose»  o  Ctrl+S\n6. El editor te sugiere la siguiente pose","en":"1. Press \"New living animation\"\n2. Choose to draw (Pixels/Free), or import an already-made .alpack pack\n3. In the editor, type the pose name in the bottom field (e.g: walk)\n4. Draw the frames for that action\n5. Press \"Save pose\"  or  Ctrl+S\n6. The editor suggests the next pose","pt":"1. Toque em \"Nova animação com vida\"\n2. Escolha desenhar (Pixels/Livre), ou importar um pacote .alpack já pronto\n3. No editor, digite o nome da pose no campo inferior (ex: walk)\n4. Desenhe os quadros dessa ação\n5. Toque em \"Salvar pose\"  ou  Ctrl+S\n6. O editor sugere a próxima pose","fr":"1. Appuyez sur « Nouvelle animation vivante »\n2. Choisissez de dessiner (Pixels/Libre), ou d'importer un pack .alpack déjà prêt\n3. Dans l'éditeur, tapez le nom de la pose dans le champ du bas (ex : walk)\n4. Dessinez les images de cette action\n5. Appuyez sur « Sauvegarder la pose »  ou  Ctrl+S\n6. L'éditeur suggère la pose suivante","de":"1. Auf „Neue lebendige Animation“ tippen\n2. Zeichnen wählen (Pixel/Frei), oder ein fertiges .alpack-Paket importieren\n3. Im Editor unten den Posennamen eingeben (z. B.: walk)\n4. Die Frames dieser Aktion zeichnen\n5. „Pose speichern“ drücken  oder  Strg+S\n6. Der Editor schlägt die nächste Pose vor","ja":"1.「新しい生きアニメ」を押す\n2. 描く(ピクセル/自由)、または既存の.alpackパックをインポート\n3. エディタ下部の欄にポーズ名を入力(例:walk)\n4. そのアクションのフレームを描く\n5.「ポーズを保存」を押すか Ctrl+S\n6. エディタが次のポーズを提案します","zh":"1. 点击「新建生动动画」\n2. 选择绘制(像素/自由),或导入已有的.alpack包\n3. 在编辑器底部的字段中输入动作名称(例如:walk)\n4. 绘制该动作的帧\n5. 点击「保存动作」或按 Ctrl+S\n6. 编辑器会建议下一个动作"},
    "guide_add_existing":   {"es":"Para agregar poses a una mascota ya creada, usa los botones «Píxeles» / «Libre» en su tarjeta, dentro de la pestaña Con vida.","en":"To add poses to an already-created mascot, use the «Pixels» / «Free» buttons on its card, in the Living tab.","pt":"Para adicionar poses a uma mascote já criada, use os botões «Pixels» / «Livre» no seu cartão, na aba Com vida.","fr":"Pour ajouter des poses à une mascotte déjà créée, utilisez les boutons « Pixels » / « Libre » sur sa carte, dans l'onglet Avec vie.","de":"Um Posen zu einem bereits erstellten Maskottchen hinzuzufügen, die Schaltflächen „Pixel“ / „Frei“ auf seiner Karte im Tab „Mit Leben“ verwenden.","ja":"既に作成済みのマスコットにポーズを追加するには、「生き生き」タブのカード上にある「ピクセル」/「自由」ボタンを使ってください。","zh":"要给已创建的吉祥物添加动作,在「有生命」标签页中该卡片上使用「像素」/「自由」按钮。"},
    "guide_title_folder":   {"es":"IMPORTAR DESDE CARPETA","en":"IMPORT FROM FOLDER","pt":"IMPORTAR DE PASTA","fr":"IMPORTER DEPUIS UN DOSSIER","de":"AUS ORDNER IMPORTIEREN","ja":"フォルダからインポート","zh":"从文件夹导入"},
    "guide_folder_intro":   {"es":"Si ya tienes los PNGs listos, usa «Importar → Carpeta de mascota».\n\nEstructura esperada:","en":"If you already have the PNGs ready, use «Import → Mascot folder».\n\nExpected structure:","pt":"Se já tem os PNGs prontos, use «Importar → Pasta de mascote».\n\nEstrutura esperada:","fr":"Si vous avez déjà les PNG prêts, utilisez « Importer → Dossier de mascotte ».\n\nStructure attendue :","de":"Falls die PNGs schon fertig sind, „Importieren → Maskottchenordner“ verwenden.\n\nErwartete Struktur:","ja":"PNGファイルが既に用意できている場合は、「インポート → マスコットフォルダ」を使ってください。\n\n想定される構成:","zh":"如果PNG文件已经准备好了,使用「导入 → 吉祥物文件夹」。\n\n预期结构:"},
    "guide_png_note":       {"es":"Los PNGs deben tener fondo transparente (RGBA). El tamaño de todos los frames de una pose debe ser igual.","en":"PNGs must have a transparent background (RGBA). All frames of a pose must be the same size.","pt":"Os PNGs devem ter fundo transparente (RGBA). O tamanho de todos os quadros de uma pose deve ser igual.","fr":"Les PNG doivent avoir un fond transparent (RGBA). Toutes les images d'une pose doivent avoir la même taille.","de":"PNGs müssen einen transparenten Hintergrund (RGBA) haben. Alle Frames einer Pose müssen gleich groß sein.","ja":"PNGは透明な背景(RGBA)である必要があります。1つのポーズの全フレームは同じサイズにしてください。","zh":"PNG必须具有透明背景(RGBA)。同一动作的所有帧尺寸必须相同。"},
    "understood_btn":       {"es":"Entendido","en":"Got it","pt":"Entendi","fr":"Compris","de":"Verstanden","ja":"わかりました","zh":"知道了"},
    "add_poses_editor":     {"es":"Añadir poses en editor","en":"Add poses in editor","pt":"Adicionar poses no editor","fr":"Ajouter des poses dans l'éditeur","de":"Posen im Editor hinzufügen","ja":"エディタでポーズを追加","zh":"在编辑器中添加动作"},
    "done_btn":             {"es":"Listo","en":"Done","pt":"Pronto","fr":"Terminé","de":"Fertig","ja":"完了","zh":"完成"},
    "gpu_warning":        {"es":"No se detectó aceleración gráfica por hardware: con varias mascotas activas a la vez alguna puede parpadear o desaparecer intermitentemente (limitación del compositor de este escritorio sin GPU, no de AnimaLinux). Se recomienda dejar solo una activa.","en":"No hardware graphics acceleration detected: with several mascots active at once, one may flicker or disappear intermittently (a limitation of this desktop's compositor without a GPU, not of AnimaLinux). It's recommended to keep only one active.","pt":"Não foi detectada aceleração gráfica por hardware: com várias mascotes ativas ao mesmo tempo, alguma pode piscar ou desaparecer intermitentemente (limitação do compositor deste desktop sem GPU, não do AnimaLinux). Recomenda-se deixar só uma ativa.","fr":"Aucune accélération graphique matérielle détectée : avec plusieurs mascottes actives en même temps, l'une peut clignoter ou disparaître par intermittence (limitation du compositeur de ce bureau sans GPU, pas d'AnimaLinux). Il est recommandé de n'en laisser qu'une active.","de":"Keine Hardware-Grafikbeschleunigung erkannt: Bei mehreren gleichzeitig aktiven Maskottchen kann eines zeitweise flackern oder verschwinden (eine Einschränkung des Compositors dieses Desktops ohne GPU, nicht von AnimaLinux). Es wird empfohlen, nur eines aktiv zu lassen.","ja":"ハードウェアグラフィックアクセラレーションが検出されませんでした。複数のマスコットを同時に有効にすると、点滅したり断続的に消えたりすることがあります(GPUのないこのデスクトップのコンポジタの制限であり、AnimaLinuxの問題ではありません)。1つだけ有効にすることをお勧めします。","zh":"未检测到硬件图形加速:同时启用多个吉祥物时,某个可能会间歇性闪烁或消失(这是没有GPU的桌面合成器的限制,不是AnimaLinux的问题)。建议只启用一个。"},
    "gen_poses":            {"es":"Generar poses","en":"Generate poses","pt":"Gerar poses","fr":"Générer des poses","de":"Posen generieren","ja":"ポーズ生成","zh":"生成动作"},
    "poses_label":          {"es":"Poses: ","en":"Poses: ","pt":"Poses: ","fr":"Poses : ","de":"Posen: ","ja":"ポーズ: ","zh":"动作: "},
    "no_anims":             {"es":"Sin animaciones todavía — crea la primera arriba.","en":"No animations yet — create the first one above.","pt":"Sem animações ainda — crie a primeira acima.","fr":"Aucune animation — créez la première ci-dessus.","de":"Keine Animationen — erstellen Sie die erste oben.","ja":"アニメなし — 上から最初のを作成してください。","zh":"还没有动画 — 在上方创建第一个。"},
    "processing":           {"es":"Procesando…","en":"Processing…","pt":"Processando…","fr":"Traitement…","de":"Verarbeitung…","ja":"処理中…","zh":"处理中…"},
    "error":                {"es":"Error: ","en":"Error: ","pt":"Erro: ","fr":"Erreur : ","de":"Fehler: ","ja":"エラー: ","zh":"错误: "},

    # ── proyectos ──────────────────────────────────────────────────────────────
    "projects_title":       {"es":"Continuar proyecto","en":"Continue project","pt":"Continuar projeto","fr":"Continuer le projet","de":"Projekt fortsetzen","ja":"プロジェクト再開","zh":"继续项目"},
    "projects_empty":       {"es":"No hay proyectos guardados.\nGuarda uno con Ctrl+Shift+S en el editor.","en":"No saved projects found.\nSave one with Ctrl+Shift+S in the editor.","pt":"Nenhum projeto salvo.\nSalve um com Ctrl+Shift+S no editor.","fr":"Aucun projet sauvegardé.\nSauvegardez avec Ctrl+Maj+S dans l'éditeur.","de":"Keine gespeicherten Projekte.\nSpeichern Sie mit Strg+Umschalt+S im Editor.","ja":"保存済みプロジェクトなし。\nエディタでCtrl+Shift+Sで保存。","zh":"没有已保存的项目。\n在编辑器中按Ctrl+Shift+S保存。"},
    "projects_open":        {"es":"Abrir","en":"Open","pt":"Abrir","fr":"Ouvrir","de":"Öffnen","ja":"開く","zh":"打开"},
    "projects_folder":      {"es":"Ver carpeta","en":"Open folder","pt":"Ver pasta","fr":"Voir le dossier","de":"Ordner öffnen","ja":"フォルダを開く","zh":"打开文件夹"},
    "projects_modified":    {"es":"Modificado:","en":"Modified:","pt":"Modificado:","fr":"Modifié :","de":"Geändert:","ja":"変更日:","zh":"修改时间:"},

    # ── configuración / idioma ─────────────────────────────────────────────────
    "settings_title":       {"es":"Configuración","en":"Settings","pt":"Configurações","fr":"Paramètres","de":"Einstellungen","ja":"設定","zh":"设置"},
    "lang_label":           {"es":"Idioma / Language:","en":"Language:","pt":"Idioma:","fr":"Langue :","de":"Sprache:","ja":"言語:","zh":"语言:"},
    "lang_restart":         {"es":"(El cambio se aplica al reabrir las ventanas)","en":"(Change applies when reopening windows)","pt":"(A mudança é aplicada ao reabrir as janelas)","fr":"(Le changement s'applique à la réouverture des fenêtres)","de":"(Änderung gilt nach erneutem Öffnen der Fenster)","ja":"(変更はウィンドウを再度開くと適用されます)","zh":"(更改在重新打开窗口后生效)"},
    "autostart_label":      {"es":"Iniciar al encender el sistema","en":"Start when the system boots","pt":"Iniciar ao ligar o sistema","fr":"Démarrer au lancement du système","de":"Beim Systemstart starten","ja":"システム起動時に開始","zh":"开机时启动"},
    "autostart_hint":       {"es":"(Se aplica al próximo inicio de sesión)","en":"(Applies at the next login)","pt":"(Aplica-se no próximo login)","fr":"(S'applique à la prochaine connexion)","de":"(Gilt ab der nächsten Anmeldung)","ja":"(次回のログインから適用)","zh":"(将在下次登录时生效)"},
    "ok":                   {"es":"Aceptar","en":"OK","pt":"OK","fr":"OK","de":"OK","ja":"OK","zh":"确定"},
    "cancel":               {"es":"Cancelar","en":"Cancel","pt":"Cancelar","fr":"Annuler","de":"Abbrechen","ja":"キャンセル","zh":"取消"},

    # ── editor de pintura ──────────────────────────────────────────────────────
    "paint_title":          {"es":"Editor de Pintura — AnimaLinux","en":"Paint Editor — AnimaLinux","pt":"Editor de Pintura — AnimaLinux","fr":"Éditeur de peinture — AnimaLinux","de":"Malen-Editor — AnimaLinux","ja":"ペイントエディタ — AnimaLinux","zh":"绘画编辑器 — AnimaLinux"},
    "save_pose_btn":        {"es":"Guardar pose","en":"Save pose","pt":"Salvar pose","fr":"Sauvegarder la pose","de":"Pose speichern","ja":"ポーズを保存","zh":"保存动作"},
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
    "save_project_btn":     {"es":"Proyecto","en":"Project","pt":"Projeto","fr":"Projet","de":"Projekt","ja":"プロジェクト","zh":"项目"},
    "open_project_btn":     {"es":"Proyecto","en":"Project","pt":"Projeto","fr":"Projet","de":"Projekt","ja":"プロジェクト","zh":"项目"},

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
