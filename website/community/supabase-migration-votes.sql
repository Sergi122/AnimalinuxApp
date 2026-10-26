-- ══════════════════════════════════════════════════════════════════════
-- Migración: votos («me gusta») + contador de descargas que SÍ suma
-- Ejecutar en: Dashboard de Supabase → SQL Editor → New query → Run
-- (seguro de re-correr: IF NOT EXISTS / OR REPLACE)
--
-- Por qué lo de las descargas: la web hacía UPDATE directo de `downloads`,
-- pero RLS solo deja actualizar al dueño autenticado, así que para cualquier
-- visitante el contador nunca subía. Ahora web y app usan la función
-- increment_pack_downloads (SECURITY DEFINER), que ya existía.
-- ══════════════════════════════════════════════════════════════════════

ALTER TABLE packs ADD COLUMN IF NOT EXISTS votes INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_packs_votes     ON packs (votes DESC);
CREATE INDEX IF NOT EXISTS idx_packs_downloads ON packs (downloads DESC);

-- Un voto por pack y por «votante». Sin cuentas obligatorias: el votante es
-- un identificador aleatorio que guarda cada navegador / cada instalación de
-- la app (no es infalible, pero evita votar dos veces por accidente).
CREATE TABLE IF NOT EXISTS pack_votes (
  pack_id    UUID NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
  voter      TEXT NOT NULL CHECK (char_length(voter) BETWEEN 16 AND 64),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (pack_id, voter)
);
ALTER TABLE pack_votes ENABLE ROW LEVEL SECURITY;
-- nadie lee ni escribe la tabla directamente: solo a través de vote_pack()

CREATE OR REPLACE FUNCTION vote_pack(p_pack UUID, p_voter TEXT, p_on BOOLEAN DEFAULT TRUE)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE n INTEGER;
BEGIN
  IF p_voter IS NULL OR char_length(p_voter) NOT BETWEEN 16 AND 64 THEN
    RAISE EXCEPTION 'votante inválido';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM packs WHERE id = p_pack AND verified) THEN
    RAISE EXCEPTION 'pack inexistente';
  END IF;
  IF p_on THEN
    INSERT INTO pack_votes (pack_id, voter) VALUES (p_pack, p_voter)
    ON CONFLICT DO NOTHING;
  ELSE
    DELETE FROM pack_votes WHERE pack_id = p_pack AND voter = p_voter;
  END IF;
  SELECT count(*) INTO n FROM pack_votes WHERE pack_id = p_pack;
  UPDATE packs SET votes = n WHERE id = p_pack;
  RETURN n;
END;
$$;
GRANT EXECUTE ON FUNCTION vote_pack(UUID, TEXT, BOOLEAN) TO anon, authenticated;

-- (por si la base se creó antes de que existiera)
CREATE OR REPLACE FUNCTION increment_pack_downloads(pack_id UUID)
RETURNS void
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  UPDATE packs SET downloads = downloads + 1 WHERE id = pack_id AND verified;
$$;
GRANT EXECUTE ON FUNCTION increment_pack_downloads(UUID) TO anon, authenticated;
