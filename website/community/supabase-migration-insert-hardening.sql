-- ════════════════════════════════════════════════════════════════════════
--  Endurecer la subida anónima (auditoría 2026-11-02)
--
--  PROBLEMA: la política "packs_public_insert" solo comprueba user_id, así
--  que cualquiera con la clave pública puede insertar una fila con
--  verified = true (se salta la moderación: la galería solo muestra las
--  verificadas) o con downloads/votes inventados.
--
--  ARREGLO: al insertar, las columnas que solo debe tocar el servidor tienen
--  que venir con su valor inicial. La app y la web ya insertan así, no cambia
--  nada para ellas.
--
--  Correr UNA vez en Supabase → SQL Editor. Es seguro repetirlo.
-- ════════════════════════════════════════════════════════════════════════

DROP POLICY IF EXISTS "packs_public_insert" ON packs;
CREATE POLICY "packs_public_insert"
  ON packs FOR INSERT
  TO anon, authenticated
  WITH CHECK (
        (user_id IS NULL OR auth.uid() = user_id)
    AND verified = false
    AND coalesce(downloads, 0) = 0
    AND coalesce(votes, 0) = 0
  );

-- Los dueños tampoco pueden autoverificarse ni tocar contadores al editar.
DROP POLICY IF EXISTS "packs_own_update" ON packs;
CREATE POLICY "packs_own_update"
  ON packs FOR UPDATE
  TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id AND verified = false);

-- Nota (no se cambia aquí, es una decisión de diseño): vote_pack() acepta
-- cualquier identificador de votante, así que un script puede inflar votos
-- inventando identificadores; lo mismo con increment_pack_downloads(). Si eso
-- llega a importar, limitar por IP con una Edge Function.
