-- Limpieza de la galería (05-nov-2026): quitar Kaoruko y las versiones viejas
-- que reemplazan las mascotas nuevas. Correr en Supabase → SQL Editor.
DELETE FROM packs WHERE id IN (
  'f4a023d7-d669-4959-a9b7-03ebe03d02be',  -- kaoruko (GIF)
  '656bd931-b401-45f7-8caf-e8d5e9319a06',  -- Panda viejo (28-oct, antes del rediseño)
  '4ada04f3-fec0-4b28-a0b4-b3c1f207a610'   -- Claudio con ojos equivocados
);
-- Los archivos quedan en Storage sin enlazar (no se muestran). Para borrarlos
-- también: Storage → packs / previews → carpetas 6794607d-3efe-46ff-b82b-781e454e6042,
-- 02d2b69649884ec59c1f6e22d8b3fae2 y 58e1105fbaf94ea9998fbc1751cb5094.
