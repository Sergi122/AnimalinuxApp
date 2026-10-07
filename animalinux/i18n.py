"""
Sistema de internacionalización — AnimaLinux
Idiomas: es · en · pt · fr · de · ja · zh
Auto-detecta el idioma del sistema; configurable desde la app.
"""

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
    "active_poses_hint":    {"es":"Solo las poses obligatorias — dibujá o importá más (greet, kiss, angry, sleep, grab, fall…)","en":"Only the mandatory poses — draw or import more (greet, kiss, angry, sleep, grab, fall…)","pt":"Só as poses obrigatórias — desenhe ou importe mais (greet, kiss, angry, sleep, grab, fall…)","fr":"Seulement les poses obligatoires — dessinez ou importez-en d'autres (greet, kiss, angry, sleep, grab, fall…)","de":"Nur die Pflicht-Posen — mehr zeichnen oder importieren (greet, kiss, angry, sleep, grab, fall…)","ja":"必須ポーズのみ — もっと描くかインポートしてください(greet, kiss, angry, sleep, grab, fall…)","zh":"仅有必需动作 — 绘制或导入更多(greet、kiss、angry、sleep、grab、fall…)"},
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
    "guide_pose_fall":      {"es":"fall — Cae y se levanta al soltar el agarre («grab»); si no la tenés, usa «jump» de reserva","en":"fall — Falls and gets back up when the grab ends; falls back to «jump» if you don't have it","pt":"fall — Cai e se levanta ao soltar o agarrão («grab»); usa «jump» como reserva se não tiver","fr":"fall — Tombe et se relève quand la prise («grab») se termine ; utilise «jump» par défaut si absente","de":"fall — Fällt hin und steht wieder auf, wenn der Griff („grab“) endet; nutzt ersatzweise „jump“, falls nicht vorhanden","ja":"fall — 「grab」が終わると落ちて起き上がる。無ければ代わりに「jump」を使用","zh":"fall — 「grab」结束时跌落并站起来;如果没有该动作则退回使用「jump」"},
    "guide_only_default":   {"es":"«default», «walk» y «jump» son obligatorias — sin ellas la mascota no se mueve bien en modo Vida. Las demás son opcionales.","en":"«default», «walk» and «jump» are mandatory — without them the mascot won't move properly in Life mode. The rest are optional.","pt":"«default», «walk» e «jump» são obrigatórias — sem elas a mascote não se move bem no modo Vida. As demais são opcionais.","fr":"« default », « walk » et « jump » sont obligatoires — sans elles, la mascotte ne bouge pas bien en mode Vie. Les autres sont facultatives.","de":"„default“, „walk“ und „jump“ sind Pflicht — ohne sie bewegt sich das Maskottchen im Lebendig-Modus nicht richtig. Die anderen sind optional.","ja":"「default」「walk」「jump」は必須です — これらが無いと、生きているモードでマスコットがうまく動きません。他は任意です。","zh":"「default」「walk」和「jump」是必需的——没有它们,吉祥物在生动模式下无法正常移动。其余都是可选的。"},
    "badge_mandatory":      {"es":"obligatoria","en":"mandatory","pt":"obrigatória","fr":"obligatoire","de":"Pflicht","ja":"必須","zh":"必需"},
    "badge_optional":       {"es":"opcional","en":"optional","pt":"opcional","fr":"facultative","de":"optional","ja":"任意","zh":"可选"},
    "guide_folder_root":    {"es":"Estructura esperada:","en":"Expected structure:","pt":"Estrutura esperada:","fr":"Structure attendue :","de":"Erwartete Struktur:","ja":"想定される構成:","zh":"预期结构:"},
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
    "theme_title":          {"es":"Tema de color","en":"Color theme","pt":"Tema de cor","fr":"Thème de couleur","de":"Farbthema","ja":"カラーテーマ","zh":"颜色主题"},
    "theme_custom":         {"es":"Elegir otro color…","en":"Pick another color…","pt":"Escolher outra cor…","fr":"Choisir une autre couleur…","de":"Andere Farbe wählen…","ja":"別の色を選ぶ…","zh":"选择其他颜色…"},
    "theme_combo":          {"es":"Combinación calculada a partir de tu color:","en":"Combination derived from your color:","pt":"Combinação calculada a partir da sua cor:","fr":"Combinaison calculée à partir de votre couleur :","de":"Aus deiner Farbe berechnete Kombination:","ja":"選んだ色から自動計算:","zh":"根据你的颜色自动计算:"},
    "f_all":                {"es":"Todas","en":"All","pt":"Todas","fr":"Toutes","de":"Alle","ja":"すべて","zh":"全部"},
    "ctl_search":           {"es":"Buscar mascotas…","en":"Search pets…","pt":"Buscar mascotes…","fr":"Rechercher…","de":"Haustiere suchen…","ja":"検索…","zh":"搜索宠物…"},
    "ctl_new":              {"es":"Nueva mascota","en":"New pet","pt":"Novo mascote","fr":"Nouvelle mascotte","de":"Neues Haustier","ja":"新規ペット","zh":"新建宠物"},
    "ctl_import":           {"es":"Importar","en":"Import","pt":"Importar","fr":"Importer","de":"Importieren","ja":"インポート","zh":"导入"},
    "imp_gif":              {"es":"Animación GIF o imagen…","en":"GIF animation or image…","pt":"Animação GIF ou imagem…","fr":"Animation GIF ou image…","de":"GIF-Animation oder Bild…","ja":"GIFアニメまたは画像…","zh":"GIF动画或图片…"},
    "imp_video":            {"es":"Vídeo corto…","en":"Short video…","pt":"Vídeo curto…","fr":"Vidéo courte…","de":"Kurzes Video…","ja":"短い動画…","zh":"短视频…"},
    "imp_folder":           {"es":"Carpeta de mascota con vida…","en":"Living pet folder…","pt":"Pasta de mascote com vida…","fr":"Dossier de mascotte vivante…","de":"Ordner eines lebenden Haustiers…","ja":"生きペットのフォルダ…","zh":"有生命宠物文件夹…"},
    "imp_pack":             {"es":"Pack .alpack…","en":"Pack .alpack…","pt":"Pacote .alpack…","fr":"Pack .alpack…","de":"Paket .alpack…","ja":".alpack パック…","zh":".alpack 包…"},
    "imp_sheet":            {"es":"Spritesheet (tira de sprites)…","en":"Spritesheet (sprite strip)…","pt":"Spritesheet (tira de sprites)…","fr":"Spritesheet (bande de sprites)…","de":"Spritesheet (Sprite-Streifen)…","ja":"スプライトシート…","zh":"精灵图…"},
    "imp_cols":             {"es":"Columnas (0 = automático)","en":"Columns (0 = auto)","pt":"Colunas (0 = automático)","fr":"Colonnes (0 = auto)","de":"Spalten (0 = automatisch)","ja":"列数 (0 = 自動)","zh":"列数 (0 = 自动)"},
    "imp_bg":               {"es":"Quitar el fondo","en":"Remove background","pt":"Remover o fundo","fr":"Supprimer le fond","de":"Hintergrund entfernen","ja":"背景を削除","zh":"去除背景"},
    "on_desktop":           {"es":"Escritorio","en":"Desktop","pt":"Área de trabalho","fr":"Bureau","de":"Desktop","ja":"デスクトップ","zh":"桌面"},
    "card_edit":            {"es":"Editar","en":"Edit","pt":"Editar","fr":"Modifier","de":"Bearbeiten","ja":"編集","zh":"编辑"},
    "card_more":            {"es":"Más opciones","en":"More options","pt":"Mais opções","fr":"Plus d'options","de":"Weitere Optionen","ja":"その他","zh":"更多选项"},
    "card_settings":        {"es":"Ajustes","en":"Settings","pt":"Ajustes","fr":"Réglages","de":"Einstellungen","ja":"設定","zh":"设置"},
    "card_export":          {"es":"Exportar","en":"Export","pt":"Exportar","fr":"Exporter","de":"Exportieren","ja":"エクスポート","zh":"导出"},
    "card_share":           {"es":"Compartir en la comunidad","en":"Share with the community","pt":"Compartilhar com a comunidade","fr":"Partager avec la communauté","de":"Mit der Community teilen","ja":"コミュニティで共有","zh":"分享到社区"},
    "card_delete":          {"es":"Borrar","en":"Delete","pt":"Apagar","fr":"Supprimer","de":"Löschen","ja":"削除","zh":"删除"},
    "del_title":            {"es":"¿Borrar «{n}»?","en":"Delete “{n}”?","pt":"Apagar «{n}»?","fr":"Supprimer « {n} » ?","de":"„{n}“ löschen?","ja":"「{n}」を削除しますか?","zh":"删除「{n}」?"},
    "del_detail":           {"es":"Se eliminará la mascota y todos sus dibujos. No se puede deshacer.","en":"The pet and all its drawings will be removed. This cannot be undone.","pt":"O mascote e todos os desenhos serão removidos. Não pode ser desfeito.","fr":"La mascotte et tous ses dessins seront supprimés. Action irréversible.","de":"Das Haustier und alle Zeichnungen werden entfernt. Nicht rückgängig zu machen.","ja":"ペットとすべての絵が削除されます。元に戻せません。","zh":"将删除宠物及其所有绘图,无法撤销。"},
    "badge_life":           {"es":"CON VIDA","en":"LIVING","pt":"COM VIDA","fr":"VIVANTE","de":"LEBENDIG","ja":"生き","zh":"有生命"},
    "badge_gif":            {"es":"GIF","en":"GIF","pt":"GIF","fr":"GIF","de":"GIF","ja":"GIF","zh":"GIF"},
    "badge_live":           {"es":"EN EL ESCRITORIO","en":"ON DESKTOP","pt":"NA ÁREA","fr":"AU BUREAU","de":"AUF DEM DESKTOP","ja":"表示中","zh":"桌面上"},
    "meta_poses":           {"es":"{n} poses","en":"{n} poses","pt":"{n} poses","fr":"{n} poses","de":"{n} Posen","ja":"{n} ポーズ","zh":"{n} 个姿势"},
    "empty_title":          {"es":"Aún no tienes mascotas","en":"No pets yet","pt":"Você ainda não tem mascotes","fr":"Pas encore de mascotte","de":"Noch keine Haustiere","ja":"まだペットがいません","zh":"还没有宠物"},
    "empty_sub":            {"es":"Crea una, impórtala o arrastra aquí un GIF, un vídeo o un pack .alpack.","en":"Create one, import one, or drop a GIF, a video or an .alpack here.","pt":"Crie um, importe ou arraste aqui um GIF, um vídeo ou um pacote .alpack.","fr":"Créez-en une, importez-en une ou déposez ici un GIF, une vidéo ou un pack .alpack.","de":"Erstelle eines, importiere eines oder ziehe ein GIF, Video oder .alpack hierher.","ja":"作成・インポートするか、GIF・動画・.alpack をここにドロップ。","zh":"新建、导入,或把 GIF、视频、.alpack 拖到这里。"},
    "empty_cta":            {"es":"Crear mi primera mascota","en":"Create my first pet","pt":"Criar meu primeiro mascote","fr":"Créer ma première mascotte","de":"Mein erstes Haustier erstellen","ja":"最初のペットを作る","zh":"创建我的第一只宠物"},
    "empty_comm":           {"es":"Explorar la comunidad","en":"Explore the community","pt":"Explorar a comunidade","fr":"Explorer la communauté","de":"Community erkunden","ja":"コミュニティを見る","zh":"探索社区"},
    "empty_tour":           {"es":"Ver el tutorial","en":"Watch the tour","pt":"Ver o tutorial","fr":"Voir le tutoriel","de":"Tutorial ansehen","ja":"チュートリアル","zh":"查看教程"},
    "no_results":           {"es":"Sin resultados para «{q}»","en":"No results for “{q}”","pt":"Sem resultados para «{q}»","fr":"Aucun résultat pour « {q} »","de":"Keine Ergebnisse für „{q}“","ja":"「{q}」の結果なし","zh":"没有「{q}」的结果"},
    "drop_here":            {"es":"Suelta aquí para importar","en":"Drop here to import","pt":"Solte aqui para importar","fr":"Déposez ici pour importer","de":"Zum Importieren hier ablegen","ja":"ここにドロップしてインポート","zh":"拖放到这里导入"},
    "summary":              {"es":"{n} mascotas · {a} en el escritorio","en":"{n} pets · {a} on the desktop","pt":"{n} mascotes · {a} na área de trabalho","fr":"{n} mascottes · {a} au bureau","de":"{n} Haustiere · {a} auf dem Desktop","ja":"{n} 匹 · {a} 匹を表示中","zh":"{n} 只宠物 · {a} 只在桌面"},
    "create_type":          {"es":"¿Qué tipo de mascota?","en":"What kind of pet?","pt":"Que tipo de mascote?","fr":"Quel type de mascotte ?","de":"Welche Art von Haustier?","ja":"どんなペット?","zh":"什么类型的宠物?"},
    "tour_title":           {"es":"Bienvenida","en":"Welcome","pt":"Boas-vindas","fr":"Bienvenue","de":"Willkommen","ja":"ようこそ","zh":"欢迎"},
    "tour_next":            {"es":"Siguiente","en":"Next","pt":"Seguinte","fr":"Suivant","de":"Weiter","ja":"次へ","zh":"下一步"},
    "tour_back":            {"es":"Atrás","en":"Back","pt":"Voltar","fr":"Retour","de":"Zurück","ja":"戻る","zh":"上一步"},
    "tour_done":            {"es":"¡Empezar!","en":"Let's go!","pt":"Começar!","fr":"C'est parti !","de":"Los geht's!","ja":"はじめる!","zh":"开始!"},
    "tour_never":           {"es":"No volver a mostrar","en":"Don't show again","pt":"Não mostrar novamente","fr":"Ne plus afficher","de":"Nicht mehr anzeigen","ja":"今後表示しない","zh":"不再显示"},
    "help_tip":             {"es":"Tutorial de bienvenida","en":"Welcome tour","pt":"Tutorial de boas-vindas","fr":"Tutoriel de bienvenue","de":"Willkommens-Tour","ja":"ウェルカムツアー","zh":"欢迎教程"},
    "upd_auto":             {"es":"Buscar actualizaciones automáticamente","en":"Check for updates automatically","pt":"Procurar atualizações automaticamente","fr":"Rechercher les mises à jour automatiquement","de":"Automatisch nach Updates suchen","ja":"アップデートを自動で確認","zh":"自动检查更新"},
    "upd_check":            {"es":"Buscar ahora","en":"Check now","pt":"Procurar agora","fr":"Vérifier maintenant","de":"Jetzt prüfen","ja":"今すぐ確認","zh":"立即检查"},
    "upd_checking":         {"es":"Buscando…","en":"Checking…","pt":"Procurando…","fr":"Vérification…","de":"Prüfe…","ja":"確認中…","zh":"检查中…"},
    "upd_uptodate":         {"es":"Ya tienes la última versión","en":"You are up to date","pt":"Você está atualizado","fr":"Vous êtes à jour","de":"Du bist auf dem neuesten Stand","ja":"最新版です","zh":"已是最新版本"},
    "upd_nonet":            {"es":"No se pudo consultar (¿sin internet?)","en":"Could not check (offline?)","pt":"Não foi possível verificar (sem internet?)","fr":"Vérification impossible (hors ligne ?)","de":"Prüfung fehlgeschlagen (offline?)","ja":"確認できません(オフライン?)","zh":"无法检查(离线?)"},
    "upd_available":        {"es":"Nueva versión disponible: v{v}","en":"New version available: v{v}","pt":"Nova versão disponível: v{v}","fr":"Nouvelle version disponible : v{v}","de":"Neue Version verfügbar: v{v}","ja":"新バージョンあり: v{v}","zh":"有新版本: v{v}"},
    "upd_now":              {"es":"Actualizar ahora","en":"Update now","pt":"Atualizar agora","fr":"Mettre à jour","de":"Jetzt aktualisieren","ja":"今すぐ更新","zh":"立即更新"},
    "upd_working":          {"es":"Actualizando…","en":"Updating…","pt":"Atualizando…","fr":"Mise à jour…","de":"Aktualisiere…","ja":"更新中…","zh":"更新中…"},
    "upd_done":             {"es":"Actualizado a v{v}. Reiniciando…","en":"Updated to v{v}. Restarting…","pt":"Atualizado para v{v}. Reiniciando…","fr":"Mis à jour vers v{v}. Redémarrage…","de":"Auf v{v} aktualisiert. Neustart…","ja":"v{v}に更新しました。再起動中…","zh":"已更新到 v{v}。正在重启…"},
    "upd_failed":           {"es":"Falló la actualización:","en":"Update failed:","pt":"A atualização falhou:","fr":"Échec de la mise à jour :","de":"Update fehlgeschlagen:","ja":"更新に失敗:","zh":"更新失败:"},
    "upd_notify_title":     {"es":"AnimaLinux: actualización disponible","en":"AnimaLinux: update available","pt":"AnimaLinux: atualização disponível","fr":"AnimaLinux : mise à jour disponible","de":"AnimaLinux: Update verfügbar","ja":"AnimaLinux: アップデートあり","zh":"AnimaLinux:有可用更新"},
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
from .backends import current as _backend  # noqa: E402
_APP_NAME = _backend.APP_NAME

_lang: str = "es"


def _detect_system_lang() -> str:
    """Detecta el idioma del sistema y lo mapea a uno soportado."""
    try:
        from .backends import current as backend
        code = backend.system_language()
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


def _brand(text: str) -> str:
    """El producto se llama distinto según el sistema (AnimaLinux / AnimaWin):
    todos los textos están escritos con «AnimaLinux» y se adaptan al mostrarse."""
    return text.replace("AnimaLinux", _APP_NAME) if _APP_NAME != "AnimaLinux" else text


def t(key: str, **kwargs) -> str:
    """Devuelve la cadena traducida al idioma activo."""
    entry = _T.get(key)
    if entry is None:
        return key
    text = _brand(entry.get(_lang) or entry.get("es") or key)
    return text.format(**kwargs) if kwargs else text

# ── textos «sueltos» (español como clave) ──────────────────────────────────────
# tr("texto en español") devuelve el texto en el idioma activo. Las traducciones
# viven en i18n_data.TR: {español: (en, pt, fr, de, ja, zh)}. Con marcadores
# {nombre} se pasan los valores por keyword: tr("Pose «{pose}» guardada.", pose=x).
# N_("texto") solo marca el texto (para tablas a nivel de módulo, que se
# construyen antes de saber el idioma); se traduce con tr() al mostrarlo.
_TR: dict = {}
_TR_LANGS = ("en", "pt", "fr", "de", "ja", "zh")


def _load_tr():
    global _TR
    if not _TR:
        from .i18n_data import TR
        _TR = TR


def N_(s: str) -> str:
    return s


def tr(s: str, **kw) -> str:
    text = s
    if _lang != "es":
        _load_tr()
        entry = _TR.get(s)
        if entry is not None:
            try:
                text = entry[_TR_LANGS.index(_lang)] or s
            except (ValueError, IndexError):
                text = s
    text = _brand(text)
    return text.format(**kw) if kw else text
