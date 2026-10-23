# Pruebas de riesgo — Fase 4

> Pruebas de concepto de lo que puede tumbar la arquitectura ([`contexto.md`](contexto.md) §11). Cada prueba usa código temporal que se elimina al cerrar la fase.

---

## 1. Cookie de sesión en Safari y en la PWA instalada (iPhone)

**Qué se comprueba:** que la cookie `cb_session` de [`diseno-tecnico.md`](diseno-tecnico.md) §2.1 (`HttpOnly`, `Secure`, `SameSite=Lax`, 30 días, renovación pasadas 24 h) sobrevive en Safari y en la PWA añadida a la pantalla de inicio, con frontend y API en el mismo dominio.

**Código temporal:** `backend/app/poc.py` (`/api/v1/poc/cookie`), `frontend/src/pages/PruebaCookie.tsx` (`/prueba-cookie`), manifest e iconos provisionales.

### Procedimiento

Usar siempre `https://compabook.vercel.app/prueba-cookie` (la preview de Vercel pide inicio de sesión).

| # | Dónde | Pasos | Resultado esperado |
|---|---|---|---|
| A | Safari | Abrir la página, **Crear cookie**, **Ver estado** | `present: true` |
| B | Safari | Cerrar la pestaña, abrirla de nuevo, **Ver estado** | `present: true` |
| C | Safari → Compartir → *Añadir a pantalla de inicio* | Abrir desde el icono. Debe decir «Modo PWA instalada: sí». **Ver estado** | Anotar: en iOS la PWA suele tener almacenamiento separado de Safari |
| D | PWA | **Crear cookie** y **Ver estado** | `present: true` |
| E | PWA | Cerrar la app (deslizar hacia arriba) y abrirla, **Ver estado** | `present: true` |
| F | PWA | **Guardar marca en localStorage**, cerrar y abrir, **Leer marca** | La marca sigue ahí |
| G | PWA | Abrir pasadas 24 h y **Ver estado** | `present: true`, `renewed: true` |
| H | PWA | Abrir pasados 8 días sin usarla y **Ver estado** | `present: true` (el límite de 7 días de Safari afecta a lo que escribe JavaScript, no a `Set-Cookie`) |
| I | PWA | **Borrar cookie**, **Ver estado** | `present: false` |

### Resultados

| # | Resultado | Fecha | Notas |
|---|---|---|---|
| A | ✅ `present: true`, `age_seconds: 197`, `renewed: false` | 2026-10-22 | Reportado por Emile; no recuerda si fue en Safari o ya en la app |
| B | Sin probar | | |
| C | La app instalada abre en `/` (`start_url`) y no tiene barra de direcciones: hizo falta un enlace temporal en Inicio (#9) | 2026-10-22 | «Modo PWA instalada: sí». No se anotó si la cookie de Safari se veía en la app; ver C2 |
| C2 | Pendiente | | Con la cookie borrada en la app, crearla en Safari y mirar en la app el estado |
| D | ✅ `present: true` tras crear la cookie en la app | 2026-10-22 | |
| E | ✅ `present: true` tras cerrar y abrir la app | 2026-10-22 | |
| F | ✅ La marca de `localStorage` sigue tras cerrar y abrir | 2026-10-22 | |
| G | | | Pendiente: esperar 24 h |
| H | | | |
| I | | | |

**Conclusión provisional (2026-10-22):** la cookie de sesión con las opciones del diseño funciona en la PWA instalada y sobrevive a cerrar y abrir la app, con frontend y API en el mismo dominio. Siguen pendientes la renovación a las 24 h (G), la persistencia tras 8 días (H) y saber si la app comparte cookies con Safari (C2). Mientras no se completen G y H, la decisión de sesiones en base de datos con cookie sigue en pie pero no está cerrada.

---

## 2. Push al iPhone

**Qué se comprueba:** que una notificación enviada desde el backend (`pywebpush` con claves VAPID) llega al iPhone con la PWA instalada, también con la app cerrada y la pantalla bloqueada. En iOS el push solo funciona en la PWA añadida a la pantalla de inicio (iOS 16.4 o superior), nunca en una pestaña de Safari.

**Código temporal:** `backend/app/poc_push.py` (`/api/v1/poc/push/key` y `/send`), `frontend/public/sw.js` (service worker), `frontend/src/pages/PruebaPush.tsx` (`/prueba-push`).

**Configuración previa en Vercel** (proyecto `compabook`, Settings → Environment Variables, entorno *Production*; después, *Redeploy*):

| Variable | Valor |
|---|---|
| `VAPID_PUBLIC_KEY` | Clave pública (65 bytes en base64url) |
| `VAPID_PRIVATE_KEY` | Clave privada (32 bytes en base64url). **Solo en Vercel**, nunca en el repositorio ni en un chat |

`VAPID_SUBJECT` es opcional: por defecto es `https://compabook.vercel.app`.

El envío solo admite suscripciones de los servicios de push de Apple, Google, Mozilla y Microsoft, para que el endpoint no sirva de proxy. No se guarda ninguna suscripción.

### Procedimiento

Usar `https://compabook.vercel.app` desde la **app instalada** (en Inicio, enlace «Prueba de push»). Si la app ya estaba instalada, cerrarla y abrirla para que cargue la versión nueva.

| # | Pasos | Resultado esperado |
|---|---|---|
| P1 | **Ver estado** | «PWA instalada: sí», soporte de push «sí» |
| P2 | **Activar notificaciones** y aceptar el aviso de iOS | Permiso `granted` y «Suscrito en web.push.apple.com» |
| P3 | **Enviar ahora** con la app abierta | Respuesta `{"sent":true}` y llega la notificación |
| P4 | **Enviar en 8 s** y cerrar la app deslizándola hacia arriba | La notificación llega con la app cerrada |
| P5 | **Enviar en 8 s** y bloquear el teléfono | La notificación llega en la pantalla de bloqueo |
| P6 | Tocar la notificación | Abre la app |
| P7 | Pasadas varias horas, repetir P4 | Sigue llegando (la suscripción no caduca) |

### Resultados

| # | Resultado | Fecha | Notas |
|---|---|---|---|
| P1 | | | |
| P2 | | | |
| P3 | | | |
| P4 | | | |
| P5 | | | |
| P6 | | | |
| P7 | | | |

**Conclusión:** _pendiente_

## 3. `pg_cron` → `pg_net` → Vercel

_Pendiente (necesita el proyecto `compabook-prod` de Supabase)._
