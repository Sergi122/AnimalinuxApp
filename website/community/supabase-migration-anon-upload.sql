-- ══════════════════════════════════════════════════════════════════════
-- Migración: permitir subir packs SIN iniciar sesión
-- Ejecutar en: Dashboard de Supabase → SQL Editor → New query → Run
-- (una sola vez; es seguro volver a correrlo, usa DROP POLICY IF EXISTS)
--
-- Qué NO cambia: validate-pack sigue revisando cada pack igual (rutas
-- permitidas, PNG real, límite de tamaño/frames, anti zip-bomb) antes de
-- que aparezca en la galería — subir sin cuenta no salta esa revisión.
-- ══════════════════════════════════════════════════════════════════════

DROP POLICY IF EXISTS "packs_auth_insert" ON packs;
CREATE POLICY "packs_public_insert"
  ON packs FOR INSERT
  TO anon, authenticated
  WITH CHECK (user_id IS NULL OR auth.uid() = user_id);

DROP POLICY IF EXISTS "packs_storage_auth_insert" ON storage.objects;
CREATE POLICY "packs_storage_public_insert"
  ON storage.objects FOR INSERT
  TO anon, authenticated
  WITH CHECK (bucket_id IN ('packs', 'previews'));
