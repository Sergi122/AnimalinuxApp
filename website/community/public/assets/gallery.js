// ── Galería ───────────────────────────────────────────────────────────
const ALL_POSES = ["default", "idle", "walk", "greet", "kiss", "jump", "angry", "grab", "fall"];

let allPacks = [];
let activeFilter = "";
let activeMode   = "";   // "" | "vida" | "sinvida"
let searchQuery  = "";

function isVidaPack(pack) {
  const poses = pack.poses || [];
  return poses.length > 1 || (poses.length === 1 && poses[0] !== "default");
}

async function loadGallery() {
  const { data, error } = await sb
    .from("packs")
    .select("*")
    .eq("verified", true)
    .order("created_at", { ascending: false });

  if (error) {
    document.getElementById("gallery").innerHTML =
      `<p class="loading-msg" style="color:var(--red)">Error cargando galería: ${error.message}</p>`;
    return;
  }

  allPacks = data || [];
  renderGallery();
}

function buildCard(pack, tpl) {
  const card = tpl.content.cloneNode(true);

  // Preview: alpack/mp4 usan preview_path (imagen estática); un GIF anima
  // solo dentro de <img>, así que se usa directamente el archivo principal.
  const img = card.querySelector(".preview-img");
  if (pack.kind === "gif") {
    const { data } = sb.storage.from(STORAGE_BUCKET_PACKS).getPublicUrl(pack.file_path);
    img.src = data.publicUrl;
    img.alt = pack.name;
  } else if (pack.preview_path) {
    const { data } = sb.storage.from(STORAGE_BUCKET_PREVIEWS).getPublicUrl(pack.preview_path);
    img.src = data.publicUrl;
    img.alt = pack.name;
  } else {
    img.src = "assets/no-preview.png";
    img.classList.add("no-img");
    img.alt = "Sin preview";
  }

  // Pose count badge + modo vida
  const poses = pack.poses || [];
  const isVida = isVidaPack(pack);
  const kindLabel = pack.kind === "gif" ? "🎞 GIF" : pack.kind === "mp4" ? "🎬 MP4" : "🎞 Simple";
  const poseCountEl = card.querySelector(".pose-count");
  poseCountEl.textContent = isVida
    ? `✦ Con vida · ${poses.length} poses`
    : kindLabel;
  poseCountEl.style.background = isVida
    ? "rgba(124,111,224,0.7)"
    : "rgba(0,0,0,0.55)";

  // Nombre y autor
  card.querySelector(".card-name").textContent = pack.name;
  card.querySelector(".card-author").textContent = pack.author
    ? `por ${pack.author}`
    : "";

  // Descripción
  const descEl = card.querySelector(".card-desc");
  descEl.textContent = pack.description || "";
  if (!pack.description) descEl.style.display = "none";

  // Badges de poses (solo tiene sentido en packs con vida; los simples no
  // traen más que "default", así que se omite la fila de badges)
  const posesEl = card.querySelector(".card-poses");
  if (isVida) {
    for (const p of ALL_POSES) {
      const b = document.createElement("span");
      b.className = "pose-badge" + (poses.includes(p) ? " has" : "");
      b.textContent = p;
      posesEl.appendChild(b);
    }
  } else {
    posesEl.style.display = "none";
  }

  // Downloads
  card.querySelector(".card-downloads").textContent =
    `⬇ ${pack.downloads ?? 0} descargas`;

  // Click en la tarjeta → página de detalle
  const article = card.querySelector(".pack-card");
  article.style.cursor = "pointer";
  article.addEventListener("click", e => {
    if (e.target.closest(".btn-download")) return;
    window.location.href = `pack.html?id=${pack.id}`;
  });

  // Botón descargar (sin navegar a detalle)
  const dlBtn = card.querySelector(".btn-download");
  dlBtn.addEventListener("click", e => {
    e.preventDefault();
    e.stopPropagation();
    downloadPack(pack);
  });

  return card;
}

function renderSection(packs, gridId, emptyId) {
  const grid  = document.getElementById(gridId);
  const empty = document.getElementById(emptyId);
  const tpl   = document.getElementById("pack-card-tpl");

  grid.innerHTML = "";
  if (packs.length === 0) {
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");
  for (const pack of packs) grid.appendChild(buildCard(pack, tpl));
}

function renderGallery() {
  const filtered = allPacks.filter(p => {
    const matchSearch = !searchQuery ||
      p.name.toLowerCase().includes(searchQuery) ||
      (p.description || "").toLowerCase().includes(searchQuery) ||
      (p.author || "").toLowerCase().includes(searchQuery);
    const matchPose = !activeFilter ||
      (p.poses || []).includes(activeFilter);
    return matchSearch && matchPose;
  });

  const vidaPacks    = filtered.filter(isVidaPack);
  const sinVidaPacks = filtered.filter(p => !isVidaPack(p));

  const sectionVida    = document.getElementById("section-vida");
  const sectionSinVida = document.getElementById("section-sinvida");
  const globalEmpty    = document.getElementById("empty-msg");

  sectionVida.classList.toggle("hidden", activeMode === "sinvida");
  sectionSinVida.classList.toggle("hidden", activeMode === "vida");

  if (activeMode !== "sinvida") renderSection(vidaPacks, "gallery-vida", "empty-vida");
  if (activeMode !== "vida")    renderSection(sinVidaPacks, "gallery-sinvida", "empty-sinvida");

  globalEmpty.classList.toggle("hidden", filtered.length !== 0);
}

async function downloadPack(pack) {
  // Incrementar contador
  await sb.from("packs")
    .update({ downloads: (pack.downloads || 0) + 1 })
    .eq("id", pack.id);

  // Descargar archivo
  const { data } = sb.storage
    .from(STORAGE_BUCKET_PACKS)
    .getPublicUrl(pack.file_path);

  const ext = pack.kind === "gif" ? "gif" : pack.kind === "mp4" ? "mp4" : "alpack";
  const a = document.createElement("a");
  a.href = data.publicUrl;
  a.download = pack.name.replace(/\s+/g, "_") + "." + ext;
  document.body.appendChild(a);
  a.click();
  a.remove();

  // Refrescar contador en local
  pack.downloads = (pack.downloads || 0) + 1;
}

// ── Eventos ───────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  loadGallery();

  // Búsqueda con debounce
  let searchTimer;
  document.getElementById("search")?.addEventListener("input", e => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      searchQuery = e.target.value.trim().toLowerCase();
      renderGallery();
    }, 250);
  });

  // Filtro por poses
  const poseFilters = document.getElementById("pose-filters");
  poseFilters?.addEventListener("click", e => {
    const pill = e.target.closest(".pill");
    if (!pill) return;
    poseFilters.querySelectorAll(".pill").forEach(p => p.classList.remove("active"));
    pill.classList.add("active");
    activeFilter = pill.dataset.pose;
    renderGallery();
  });

  // Filtro por modo (Con vida / Sin vida / Todas)
  const modeFilters = document.getElementById("mode-filters");
  modeFilters?.addEventListener("click", e => {
    const pill = e.target.closest(".pill");
    if (!pill) return;
    modeFilters.querySelectorAll(".pill").forEach(p => p.classList.remove("active"));
    pill.classList.add("active");
    activeMode = pill.dataset.mode;
    renderGallery();
  });
});
