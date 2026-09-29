-- ══════════════════════════════════════════════════════════════════════
-- Migración: aceptar también .gif y .mp4 (además de .alpack)
-- Ejecutar en: Dashboard de Supabase → SQL Editor → New query → Run
-- (una sola vez; usa IF NOT EXISTS / UPDATE, es seguro re-correrlo)
-- ══════════════════════════════════════════════════════════════════════

-- Nueva columna: qué tipo de archivo es este pack
ALTER TABLE packs ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'alpack';
ALTER TABLE packs DROP CONSTRAINT IF EXISTS packs_kind_check;
ALTER TABLE packs ADD CONSTRAINT packs_kind_check CHECK (kind IN ('alpack', 'gif', 'mp4'));

-- El bucket "packs" ahora también acepta GIF y MP4 (antes solo zip)
UPDATE storage.buckets
SET allowed_mime_types = ARRAY['application/zip', 'application/octet-stream', 'image/gif', 'video/mp4']
WHERE id = 'packs';
