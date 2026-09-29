-- ══════════════════════════════════════════════════════════════════════
-- AnimaLinux Community — Setup de Supabase
-- Ejecuta este SQL en: Dashboard → SQL Editor → New query
-- ══════════════════════════════════════════════════════════════════════

-- Tabla principal de packs
CREATE TABLE IF NOT EXISTS packs (
  id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  name         TEXT NOT NULL CHECK (char_length(name) <= 60),
  description  TEXT CHECK (char_length(description) <= 300),
  author       TEXT CHECK (char_length(author) <= 60),
  fps          INTEGER DEFAULT 12 CHECK (fps BETWEEN 1 AND 60),
  poses        TEXT[] DEFAULT '{}',
  tags         TEXT[] DEFAULT '{}',
  file_path    TEXT NOT NULL,
  preview_path TEXT,
  file_size    INTEGER CHECK (file_size <= 52428800),  -- 50 MB máximo
  downloads    INTEGER DEFAULT 0,
  verified     BOOLEAN DEFAULT FALSE,  -- true solo tras validación server-side
  user_id      UUID REFERENCES auth.users(id) ON DELETE SET NULL
);

-- Índices para búsqueda rápida
CREATE INDEX IF NOT EXISTS idx_packs_name       ON packs USING gin(to_tsvector('spanish', name));
CREATE INDEX IF NOT EXISTS idx_packs_created_at ON packs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_packs_poses      ON packs USING gin(poses);

-- Row Level Security (RLS)
ALTER TABLE packs ENABLE ROW LEVEL SECURITY;

-- Galería pública: solo packs ya verificados por validate-pack.
-- El propio autor también ve su fila mientras está pendiente de verificación.
CREATE POLICY "packs_public_read"
  ON packs FOR SELECT
  USING (verified = true OR auth.uid() = user_id);

-- Subir NO requiere iniciar sesión (menos fricción para compartir). Si estás
-- logueado, tu user_id queda registrado (podés borrar/editar después); si no,
-- el pack queda sin dueño. Cualquiera de los dos casos pasa igual por
-- validate-pack antes de aparecer en la galería pública.
CREATE POLICY "packs_public_insert"
  ON packs FOR INSERT
  TO anon, authenticated
  WITH CHECK (user_id IS NULL OR auth.uid() = user_id);

-- Los usuarios solo pueden actualizar sus propios packs (no reasignar user_id
-- ni auto-verificarse: esos campos los toca únicamente validate-pack con la
-- service_role key, que salta RLS).
CREATE POLICY "packs_own_update"
  ON packs FOR UPDATE
  TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- Los usuarios solo pueden borrar sus propios packs
CREATE POLICY "packs_own_delete"
  ON packs FOR DELETE
  TO authenticated
  USING (auth.uid() = user_id);

-- Contador de descargas: incremento atómico vía RPC, no vía UPDATE directo
-- (así no hace falta abrir la tabla a updates anónimos).
CREATE OR REPLACE FUNCTION increment_pack_downloads(pack_id UUID)
RETURNS void
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  UPDATE packs SET downloads = downloads + 1 WHERE id = pack_id;
$$;

GRANT EXECUTE ON FUNCTION increment_pack_downloads(UUID) TO anon, authenticated;

-- ── Storage buckets ────────────────────────────────────────────────────
-- Crear en: Dashboard → Storage → New bucket
-- Bucket "packs"    → Public: ON  → Max file size: 52428800 (50 MB)
-- Bucket "previews" → Public: ON  → Max file size: 2097152  (2 MB)

-- Políticas de storage para "packs"
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES
  ('packs',    'packs',    true, 52428800, ARRAY['application/zip', 'application/octet-stream']),
  ('previews', 'previews', true, 2097152,  ARRAY['image/png', 'image/webp'])
ON CONFLICT (id) DO NOTHING;

CREATE POLICY "packs_storage_public_read"
  ON storage.objects FOR SELECT
  USING (bucket_id IN ('packs', 'previews'));

CREATE POLICY "packs_storage_public_insert"
  ON storage.objects FOR INSERT
  TO anon, authenticated
  WITH CHECK (bucket_id IN ('packs', 'previews'));

CREATE POLICY "packs_storage_own_delete"
  ON storage.objects FOR DELETE
  TO authenticated
  USING (bucket_id IN ('packs', 'previews') AND auth.uid()::text = (storage.foldername(name))[1]);
