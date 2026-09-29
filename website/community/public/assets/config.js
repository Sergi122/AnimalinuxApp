// ── Configuración de Supabase ─────────────────────────────────────────
// Reemplaza estos valores con los de tu proyecto en supabase.com
// Dashboard → Settings → API
const SUPABASE_URL  = "https://vutmbldvzgqcqenuzjav.supabase.co";
const SUPABASE_ANON = "sb_publishable_TpezmyjjZmEoDeP47E8h7A_IjJ4maa9";

const STORAGE_BUCKET_PACKS    = "packs";     // .alpack files
const STORAGE_BUCKET_PREVIEWS = "previews";  // PNG thumbnails

const MAX_FILE_MB = 50;

// Inicializar cliente Supabase (disponible globalmente)
const sb = supabase.createClient(SUPABASE_URL, SUPABASE_ANON);
