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
| C2 | ✅ `present: false` en la app tras crear la cookie en Safari: **no comparten cookies** | 2026-10-22 | Con la cookie borrada en la app, se creó en Safari y se miró en la app. Es el comportamiento habitual de iOS. Efecto: quien instale la app debe iniciar sesión dentro de ella |
| D | ✅ `present: true` tras crear la cookie en la app | 2026-10-22 | |
| E | ✅ `present: true` tras cerrar y abrir la app | 2026-10-22 | |
| F | ✅ La marca de `localStorage` sigue tras cerrar y abrir | 2026-10-22 | |
| G | | | Pendiente: esperar 24 h |
| H | | | |
| I | | | |

**Conclusión provisional (2026-10-22):** la cookie de sesión con las opciones del diseño funciona en la PWA instalada y sobrevive a cerrar y abrir la app, con frontend y API en el mismo dominio. Safari y la app instalada **no comparten cookies** (C2), así que la guía de instalación (Fase 9) debe avisar de que hay que iniciar sesión dentro de la app. Siguen pendientes la renovación a las 24 h (G) y la persistencia tras 8 días (H); el reloj de ambas arranca al crear la cookie dentro de la app, sin volver a crearla ni borrarla. Mientras no se completen G y H, la decisión de sesiones en base de datos con cookie sigue en pie pero no está cerrada.

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
| P1 | ✅ | 2026-10-22 | Reportado por Emile: «funcionó todo» (sin detalle por paso) |
| P2 | ✅ | 2026-10-22 | Idem |
| P3 | ✅ | 2026-10-22 | Idem |
| P4 | ✅ | 2026-10-22 | Idem |
| P5 | ✅ | 2026-10-22 | Idem |
| P6 | ✅ | 2026-10-22 | Idem |
| P7 | Pendiente | | Repetir P4 pasadas varias horas y, mejor, al día siguiente |

**Conclusión provisional (2026-10-22):** el push funciona de extremo a extremo con la PWA instalada: `pywebpush` con claves VAPID desde una función de Vercel, service worker propio y llegada con la app cerrada y con el teléfono bloqueado. Falta confirmar que la suscripción no caduca (P7). Para la Fase 7 hay que guardar las suscripciones por usuario y marcarlas inactivas si el servicio responde 404 o 410, como ya prevé `diseno-tecnico.md` §1.6.

### Android

**2026-10-23:** el equipo probó el mismo código (`/prueba-push`) en un Android y las notificaciones funcionaron. Reportado de palabra: no se anotó el modelo, la versión de Android ni el navegador, ni si fue con la PWA instalada o desde una pestaña, ni los pasos concretos (P1 a P6). Antes de cerrar la Fase 7 hay que repetirlo con la tabla anterior y anotar esos datos.

## 3. `pg_cron` → `pg_net` → Vercel

_Pendiente (necesita el proyecto `compabook-prod` de Supabase)._
