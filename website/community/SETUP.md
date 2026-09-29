# AnimaLinux Community Web — Guía de instalación

Stack: **Supabase** (backend gratuito) + **GitHub Pages** (hosting gratuito)

---

## 1. Crear proyecto en Supabase

1. Ve a [supabase.com](https://supabase.com) → **New project**
2. Elige un nombre (ej. `animalinux-community`) y una contraseña de base de datos
3. Selecciona la región más cercana (ej. `West EU`)
4. Espera ~2 minutos a que el proyecto arranque

---

## 2. Configurar la base de datos

1. En el dashboard de Supabase: **SQL Editor → New query**
2. Copia y pega el contenido de `supabase-setup.sql`
3. Haz clic en **Run**

---

## 3. Configurar Auth (login con GitHub y Google)

### GitHub OAuth:
1. Ve a [github.com/settings/developers](https://github.com/settings/developers) → **New OAuth App**
   - Application name: `AnimaLinux Community`
   - Homepage URL: `https://TU_USUARIO.github.io/animalinux`
   - Authorization callback URL: `https://TU_PROYECTO.supabase.co/auth/v1/callback`
2. Copia el **Client ID** y genera un **Client Secret**
3. En Supabase: **Authentication → Providers → GitHub** → activa y pega las claves

### Google OAuth:
1. Ve a [console.cloud.google.com](https://console.cloud.google.com) → **APIs & Services → Credentials**
2. Crea **OAuth 2.0 Client ID** → tipo Web
   - Authorized redirect URI: `https://TU_PROYECTO.supabase.co/auth/v1/callback`
3. En Supabase: **Authentication → Providers → Google** → activa y pega las claves

---

## 4. Obtener las claves de la API

En Supabase: **Settings → API**

- **Project URL**: `https://XXXXXXXXXX.supabase.co`
- **anon public key**: `eyJhbGci…`

Edita `web/assets/config.js` y reemplaza:
```js
const SUPABASE_URL  = "https://TU_PROYECTO.supabase.co";
const SUPABASE_ANON = "TU_CLAVE_ANONIMA";
```

---

## 5. Publicar en GitHub Pages

1. Sube la carpeta `web/` a tu repo de GitHub
2. En el repo: **Settings → Pages → Source: Deploy from branch**
3. Selecciona la rama `main` y la carpeta `/web` (o `/docs` si la renombras)
4. En unos minutos estará en: `https://TU_USUARIO.github.io/animalinux/`

---

## Estructura de archivos

```
web/
├── index.html          ← Galería principal
├── upload.html         ← Subir mascota
├── SETUP.md            ← Esta guía
├── supabase-setup.sql  ← SQL para configurar Supabase
└── assets/
    ├── style.css       ← Estilos (tema oscuro)
    ├── config.js       ← URLs y claves de Supabase ← EDITAR
    ├── auth.js         ← Login / logout compartido
    ├── gallery.js      ← Carga y muestra los packs
    └── upload.js       ← Sube .alpack con preview
```

---

## ¿Qué acepta el sitio?

| Tipo | Descripción |
|------|-------------|
| `.alpack` | Pack de AnimaLinux — ZIP con `mascot.json` + carpeta `poses/` |
| Tamaño máximo | 50 MB por pack |
| Preview | Se extrae automáticamente del primer frame de la pose `default` |

### Estructura de un `.alpack`:
```
mascota.alpack (es un ZIP)
├── mascot.json
└── poses/
    ├── default/
    │   ├── frame_0000.png
    │   └── frame_0001.png
    ├── idle/
    ├── walk/
    ├── greet/
    ├── jump/
    ├── angry/
    └── grab/
```

### `mascot.json`:
```json
{
  "format": "animalinux-pack",
  "version": 1,
  "name": "Gato Pixel",
  "author": "tu_nombre",
  "fps": 12,
  "poses": ["default", "idle", "walk", "greet", "jump", "angry", "grab"]
}
```

---

## Moderación

Para revisar o borrar packs: Supabase **Dashboard → Table Editor → packs** → editar o borrar filas directamente.
