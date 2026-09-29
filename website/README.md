# Sitios web de AnimaLinux

Código de los dos sitios, desplegados en Firebase Hosting.

| Carpeta | Sitio | Proyecto Firebase |
|---|---|---|
| `landing/` | https://animalinux.web.app — presentación, instalación e historial de cambios | `animalinux` |
| `community/` | https://animalinux-community.web.app — galería para subir y bajar packs `.alpack` (Supabase) | `animalinux-community` |

Ambos son HTML/CSS/JS estáticos, sin paso de compilación. Para desplegar:

```bash
cd website/landing    # o website/community
firebase deploy --only hosting
```

La guía de Supabase de la comunidad está en `community/SETUP.md`.
