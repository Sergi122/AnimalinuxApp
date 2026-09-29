// ── Upload Page ───────────────────────────────────────────────────────
let selectedFile   = null;
let extractedMeta  = null;
let previewBlob    = null;
let selectedKind   = "alpack";   // "alpack" | "gif" | "mp4"

// ── Constantes de seguridad ───────────────────────────────────────────
const PNG_MAGIC   = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A];
const MAX_UNZIP_MB = 200;          // máximo descomprimido
const MAX_FRAMES   = 500;          // máximo frames totales en el pack
const SAFE_PATH_RE = /^poses\/[a-zA-Z0-9_-]{1,32}\/frame_\d{4}\.png$/;

function isPng(buffer) {
  const bytes = new Uint8Array(buffer.slice(0, 8));
  return PNG_MAGIC.every((b, i) => bytes[i] === b);
}

function sanitizeText(str, maxLen = 300) {
  if (typeof str !== "string") return "";
  return str.replace(/[<>"'&]/g, "").slice(0, maxLen).trim();
}

// ── Leer .alpack con JSZip ────────────────────────────────────────────
async function readAlpack(file) {
  const zip = await JSZip.loadAsync(file);

  // ── 1. Validar rutas (anti path-traversal y zip-slip) ────────────
  let totalUnzipBytes = 0;
  let frameCount = 0;
  for (const [name, entry] of Object.entries(zip.files)) {
    if (entry.dir) continue;
    if (name === "mascot.json") continue;
    // Rechazar cualquier ruta inesperada
    if (!SAFE_PATH_RE.test(name)) {
      throw new Error(`Ruta no permitida en el pack: "${name}"`);
    }
    // Anti zip-bomb: sumar tamaño descomprimido
    const uncompressed = entry._data?.uncompressedSize ?? 0;
    totalUnzipBytes += uncompressed;
    if (totalUnzipBytes > MAX_UNZIP_MB * 1024 * 1024) {
      throw new Error(`El pack descomprimido supera ${MAX_UNZIP_MB} MB. Rechazado.`);
    }
    frameCount++;
    if (frameCount > MAX_FRAMES) {
      throw new Error(`El pack tiene demasiados frames (máx ${MAX_FRAMES}).`);
    }
  }

  // ── 2. mascot.json ────────────────────────────────────────────────
  const jsonFile = zip.file("mascot.json");
  if (!jsonFile) throw new Error("El archivo no tiene mascot.json — ¿es un .alpack válido?");

  let meta;
  try {
    meta = JSON.parse(await jsonFile.async("string"));
  } catch {
    throw new Error("mascot.json está corrupto o no es JSON válido.");
  }
  if (meta.format !== "animalinux-pack") throw new Error("Formato no reconocido.");

  // Sanitizar campos de texto (evita XSS si alguien manipula el JSON)
  meta.name   = sanitizeText(meta.name,   60)  || "Sin nombre";
  meta.author = sanitizeText(meta.author, 60)  || "";
  meta.fps    = Math.max(1, Math.min(60, parseInt(meta.fps) || 12));
  if (!Array.isArray(meta.poses)) meta.poses = ["default"];
  meta.poses  = meta.poses
    .filter(p => typeof p === "string" && /^[a-zA-Z0-9_-]{1,32}$/.test(p))
    .slice(0, 20);

  // ── 3. Verificar magic bytes PNG en cada frame ────────────────────
  for (const [name, entry] of Object.entries(zip.files)) {
    if (entry.dir || name === "mascot.json") continue;
    const buf = await entry.async("arraybuffer");
    if (!isPng(buf)) {
      throw new Error(`"${name}" no es un PNG válido. Solo se aceptan imágenes PNG reales.`);
    }
  }

  // ── 4. Extraer preview (pose default, primer frame) ───────────────
  let preview = null;
  for (const candidate of ["poses/default/frame_0000.png", "poses/default/frame_000.png"]) {
    const f = zip.file(candidate);
    if (f) {
      const buf = await f.async("arraybuffer");
      preview = new Blob([buf], { type: "image/png" });
      break;
    }
  }
  if (!preview) {
    for (const [name, entry] of Object.entries(zip.files)) {
      if (name.endsWith("frame_0000.png") && !entry.dir) {
        const buf = await entry.async("arraybuffer");
        preview = new Blob([buf], { type: "image/png" });
        break;
      }
    }
  }

  return { meta, preview };
}

const GIF_MAGIC = ["GIF87a", "GIF89a"];

async function isRealGif(file) {
  const head = new Uint8Array(await file.slice(0, 6).arrayBuffer());
  const s = String.fromCharCode(...head);
  return GIF_MAGIC.includes(s);
}

async function isRealMp4(file) {
  const head = new Uint8Array(await file.slice(0, 8).arrayBuffer());
  return head[4] === 0x66 && head[5] === 0x74 && head[6] === 0x79 && head[7] === 0x70; // "ftyp"
}

function baseName(filename) {
  return filename.replace(/\.[^.]+$/, "");
}

// ── Leer un GIF: el archivo mismo sirve de preview (anima solo en <img>) ──
async function readGif(file) {
  if (!(await isRealGif(file))) {
    throw new Error("No es un GIF real (la firma del archivo no coincide).");
  }
  return {
    meta: { name: baseName(file.name), poses: ["default"], fps: 12 },
    preview: file,
  };
}

// ── Leer un MP4: capturamos un frame como preview estático (no se puede
// mostrar video dentro de <img> en la galería) ───────────────────────────
async function readMp4(file) {
  if (!(await isRealMp4(file))) {
    throw new Error("No es un MP4 real (la firma del archivo no coincide).");
  }
  const preview = await new Promise((resolve) => {
    const video = document.createElement("video");
    video.muted = true;
    video.src = URL.createObjectURL(file);
    video.addEventListener("loadeddata", () => {
      video.currentTime = Math.min(0.2, (video.duration || 1) / 2);
    });
    video.addEventListener("seeked", () => {
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth || 200;
      canvas.height = video.videoHeight || 200;
      canvas.getContext("2d").drawImage(video, 0, 0);
      canvas.toBlob((blob) => {
        URL.revokeObjectURL(video.src);
        resolve(blob);
      }, "image/png");
    });
    video.addEventListener("error", () => resolve(null));
  });
  return {
    meta: { name: baseName(file.name), poses: ["default"], fps: 24 },
    preview,
  };
}

function setError(msg) {
  const el = document.getElementById("upload-error");
  if (!msg) { el.classList.add("hidden"); return; }
  el.textContent = msg;
  el.classList.remove("hidden");
}

function setProgress(pct, label) {
  document.getElementById("progress-fill").style.width = pct + "%";
  document.getElementById("progress-label").textContent = label;
}

async function handleFile(file) {
  setError("");
  const lower = file.name.toLowerCase();
  const kind = lower.endsWith(".alpack") ? "alpack"
             : lower.endsWith(".gif")    ? "gif"
             : lower.endsWith(".mp4")    ? "mp4"
             : null;
  if (!kind) {
    setError("Solo se aceptan archivos .alpack, .gif o .mp4 exportados desde AnimaLinux.");
    return;
  }
  if (file.size > MAX_FILE_MB * 1024 * 1024) {
    setError(`El archivo supera el límite de ${MAX_FILE_MB} MB.`);
    return;
  }

  try {
    const reader = kind === "alpack" ? readAlpack : kind === "gif" ? readGif : readMp4;
    const { meta, preview } = await reader(file);
    selectedFile  = file;
    selectedKind  = kind;
    extractedMeta = meta;
    previewBlob   = preview;

    // Rellenar el nombre si el campo está vacío
    const nameField = document.getElementById("field-name");
    if (!nameField.value) nameField.value = meta.name || "";

    // Mostrar preview en drop zone
    document.getElementById("dz-idle").classList.add("hidden");
    const dzPrev = document.getElementById("dz-preview");
    dzPrev.classList.remove("hidden");

    if (preview) {
      const url = URL.createObjectURL(preview);
      document.getElementById("preview-img").src = url;
    } else {
      document.getElementById("preview-img").src = "assets/no-preview.png";
    }

    document.getElementById("preview-name").textContent = meta.name || file.name;
    document.getElementById("preview-poses").textContent = kind === "alpack"
      ? "Poses: " + (meta.poses || []).join(", ")
      : (kind === "gif" ? "🎞 GIF simple" : "🎬 Vídeo MP4");
    document.getElementById("preview-size").textContent =
      (file.size / 1024).toFixed(0) + " KB · fps: " + (meta.fps || "?");

    document.getElementById("btn-submit").disabled = false;
    checkCanSubmit();
  } catch (err) {
    setError("No se pudo leer el archivo: " + err.message);
  }
}

function checkCanSubmit() {
  const name = document.getElementById("field-name").value.trim();
  document.getElementById("btn-submit").disabled = !selectedFile || !name;
}

// ── Subida ─────────────────────────────────────────────────────────────
async function doUpload() {
  const name   = document.getElementById("field-name").value.trim();
  const desc   = document.getElementById("field-desc").value.trim();
  const tags   = document.getElementById("field-tags").value
    .split(",").map(s => s.trim()).filter(Boolean);
  const author = sanitizeText(document.getElementById("field-author").value.trim(), 60);

  setError("");
  document.getElementById("btn-submit").disabled = true;
  document.getElementById("upload-progress").classList.remove("hidden");

  try {
    const ts       = Date.now();
    // carpeta con id aleatorio — solo agrupa los archivos, no da ningún
    // permiso especial sobre ellos.
    const folder   = crypto.randomUUID ? crypto.randomUUID() : `anon-${ts}-${Math.random().toString(36).slice(2)}`;
    const ext        = selectedKind === "alpack" ? "alpack" : selectedKind === "gif" ? "gif" : "mp4";
    const mainMime   = selectedKind === "alpack" ? "application/zip"
                      : selectedKind === "gif"   ? "image/gif" : "video/mp4";
    const filePath = `${folder}/${ts}.${ext}`;
    // el GIF anima solo dentro de un <img>, no hace falta preview aparte —
    // solo alpack y mp4 necesitan una imagen estática separada
    const needsPreview = previewBlob && selectedKind !== "gif";
    const prevPath = needsPreview ? `${folder}/${ts}.png` : null;

    // 1. Subir el archivo principal
    setProgress(20, "Subiendo archivo…");
    const { error: e1 } = await sb.storage
      .from(STORAGE_BUCKET_PACKS)
      .upload(filePath, selectedFile, { contentType: mainMime, upsert: false });
    if (e1) throw e1;

    // 2. Subir preview PNG (alpack/mp4)
    if (needsPreview) {
      setProgress(50, "Subiendo preview…");
      const { error: e2 } = await sb.storage
        .from(STORAGE_BUCKET_PREVIEWS)
        .upload(prevPath, previewBlob, { contentType: "image/png", upsert: false });
      if (e2) throw e2;
    }

    // 3. Insertar en base de datos
    setProgress(80, "Guardando metadatos…");
    const { error: e3 } = await sb.from("packs").insert({
      name,
      description: desc || null,
      author,
      fps:       extractedMeta.fps    || 12,
      poses:     extractedMeta.poses  || ["default"],
      tags:      tags.length ? tags : null,
      kind:      selectedKind,
      file_path: filePath,
      preview_path: prevPath,
      file_size: selectedFile.size,
      user_id:   null,
      downloads: 0,
    });
    if (e3) throw e3;

    setProgress(100, "¡Listo!");
    await new Promise(r => setTimeout(r, 500));

    // Mostrar pantalla de éxito
    document.getElementById("screen-form").classList.add("hidden");
    document.getElementById("screen-success").classList.remove("hidden");
    document.getElementById("success-msg").textContent =
      `"${name}" fue subida correctamente. Aparecerá en la galería en unos segundos tras la validación automática.`;

  } catch (err) {
    setError("Error al subir: " + (err.message || JSON.stringify(err)));
    document.getElementById("btn-submit").disabled = false;
    document.getElementById("upload-progress").classList.add("hidden");
  }
}

// ── Eventos ────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  // Drop zone
  const dz = document.getElementById("drop-zone");
  dz?.addEventListener("dragover", e => {
    e.preventDefault();
    dz.classList.add("drag-over");
  });
  dz?.addEventListener("dragleave", () => dz.classList.remove("drag-over"));
  dz?.addEventListener("drop", e => {
    e.preventDefault();
    dz.classList.remove("drag-over");
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  });
  dz?.addEventListener("click", () => {
    if (!document.getElementById("dz-preview").classList.contains("hidden")) return;
    document.getElementById("file-input").click();
  });

  document.getElementById("file-input")?.addEventListener("change", e => {
    const file = e.target.files[0];
    if (file) handleFile(file);
  });

  document.getElementById("dz-reset")?.addEventListener("click", e => {
    e.stopPropagation();
    selectedFile = null; extractedMeta = null; previewBlob = null; selectedKind = "alpack";
    document.getElementById("dz-preview").classList.add("hidden");
    document.getElementById("dz-idle").classList.remove("hidden");
    document.getElementById("file-input").value = "";
    document.getElementById("btn-submit").disabled = true;
    setError("");
  });

  // Validar al escribir el nombre
  document.getElementById("field-name")?.addEventListener("input", checkCanSubmit);

  // Submit
  document.getElementById("btn-submit")?.addEventListener("click", doUpload);
});
