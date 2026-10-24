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
| G | ✅ | 2026-10-23 | Reportado por Emile («lo pendiente de la Fase 4 está listo»), sin el valor de `age_seconds`. La cookie se creó el 2026-10-22 por la noche |
| H | Pendiente | | Hacerlo a partir del **2026-10-30** (8 días después de crear la cookie), sin abrir **Crear** ni **Borrar** antes |
| I | Pendiente | | Después de H |

**Conclusión provisional (2026-10-23):** la cookie de sesión con las opciones del diseño funciona en la PWA instalada y sobrevive a cerrar y abrir la app, con frontend y API en el mismo dominio. Safari y la app instalada **no comparten cookies** (C2), así que la guía de instalación (Fase 9) debe avisar de que hay que iniciar sesión dentro de la app. La renovación a las 24 h (G) se dio por buena el 2026-10-23. Sigue pendiente la persistencia tras 8 días (H), que no puede hacerse antes del **2026-10-30**; hasta entonces no se debe crear ni borrar la cookie. Mientras no se complete H, la decisión de sesiones en base de datos con cookie sigue en pie pero no está cerrada.

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
| P7 | ✅ | 2026-10-23 | Reportado por Emile, sin detalle de la hora del segundo envío |

**Conclusión (2026-10-23):** el push funciona de extremo a extremo con la PWA instalada en iPhone y también en Android: `pywebpush` con claves VAPID desde una función de Vercel, service worker propio y llegada con la app cerrada y con el teléfono bloqueado. La suscripción siguió valiendo en un segundo envío (P7). Para la Fase 7 hay que guardar las suscripciones por usuario y marcarlas inactivas si el servicio responde 404 o 410, como ya prevé `diseno-tecnico.md` §1.6.

### Android

**2026-10-23:** el equipo probó el mismo código (`/prueba-push`) en un **Honor X5c** y las notificaciones funcionaron, tanto en **Brave** (pestaña del navegador) como con la **app instalada**. Reportado de palabra: no se anotó la versión de Android ni el detalle de los pasos P1 a P6. Se repetirá con la tabla anterior en la Fase 7, con el flujo real de recordatorios.

## 3. `pg_cron` → `pg_net` → Vercel

**Qué se comprueba:** que `pg_cron` en Supabase (`compabook-prod`) llama cada minuto, con `pg_net`, a un endpoint de la función de Vercel protegido por un secreto, y que la llamada queda en los registros de las dos partes. Es el criterio «`pg_cron` llama a `/internal/jobs` en producción y queda en los logs» de [`diseno-tecnico.md`](diseno-tecnico.md) §11.

**Código temporal:** `backend/app/poc_cron.py` (`POST /api/v1/internal/ping`). Compara la cabecera `X-Internal-Secret` con `INTERNAL_SECRET` en tiempo constante, no toca la base de datos y nunca registra ni devuelve el secreto. Responde 503 si `INTERNAL_SECRET` no está definida y 401 si falta o es incorrecta.

**Configuración previa:**
- Vercel (*Production*): `INTERNAL_SECRET` (cadena aleatoria larga) y `DATABASE_URL` / `DATABASE_URL_DIRECT` ya cargadas.
- Supabase: extensiones `pg_cron` y `pg_net` activadas.

### Procedimiento

| # | Dónde | Pasos | Resultado esperado |
|---|---|---|---|
| C1 | Navegador o `curl` | `POST https://compabook.vercel.app/api/v1/internal/ping` **sin** cabecera | `401` (con `503` es que falta `INTERNAL_SECRET`) |
| C2 | Supabase → SQL Editor | Guardar el secreto en Vault (SQL de abajo, pegando el valor real de `INTERNAL_SECRET`) | `create_secret` devuelve un id |
| C3 | Supabase → SQL Editor | Programar la tarea con `cron.schedule` | Devuelve el número del trabajo |
| C4 | Supabase → SQL Editor | Esperar 2–3 min y ejecutar las consultas de verificación | `cron.job_run_details`: `succeeded`; `net._http_response`: `status_code = 200` |
| C5 | Vercel → proyecto → Logs | Buscar `internal_ping` | Una línea por minuto |
| C6 | Supabase → SQL Editor | `cron.unschedule` | La tarea deja de ejecutarse |

```sql
-- C2. Guardar el secreto (sustituir por el valor real; no compartirlo ni subirlo al repositorio)
select vault.create_secret('<VALOR DE INTERNAL_SECRET>', 'internal_secret');

-- C3. Programar la llamada cada minuto
select cron.schedule(
  'compabook-ping',
  '* * * * *',
  $$
  select net.http_post(
    url     := 'https://compabook.vercel.app/api/v1/internal/ping',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'X-Internal-Secret', (select decrypted_secret from vault.decrypted_secrets where name = 'internal_secret')
    )
  );
  $$
);

-- C4. Verificar
select status, return_message, start_time from cron.job_run_details order by start_time desc limit 5;
select id, status_code, content, created from net._http_response order by created desc limit 5;

-- C6. Parar
select cron.unschedule('compabook-ping');
```

`net._http_response` guarda las respuestas durante unas horas. Si `status_code` es 401, el secreto de Vault no coincide con el de Vercel; si es 503, falta `INTERNAL_SECRET` en Vercel (¿redeploy?).

### Resultados

| # | Resultado | Fecha | Notas |
|---|---|---|---|
| C1 | ✅ `401` sin cabecera | 2026-10-23 | Comprobado por Claude con `curl`; confirma que `INTERNAL_SECRET` existe en Vercel |
| C2 | ✅ | 2026-10-23 | El primer intento dio 401: el secreto de Vault no coincidía con el de Vercel o no existía (no se llegó a distinguir; ver «Hallazgos»). Se rotó con `vault.update_secret` |
| C3 | ✅ `schedule = 1` | 2026-10-23 | Tras activar `pg_cron` y `pg_net` |
| C4 | ✅ `status_code = 200` | 2026-10-23 | Reportado por Emile. Las filas 11 y 12 quedaron con 401: son de antes de corregir el secreto y `net._http_response` no se reescribe |
| C5 | ✅ | 2026-10-23 | Reportado por Emile como «todo bien»; sin detalle de las líneas |
| C6 | Se deja corriendo | 2026-10-23 | La tarea `compabook-ping` sigue activa a propósito. **Revisar el 2026-10-30**: si Supabase pausó el proyecto, el uso en *Usage* de Vercel y Supabase, y después pararla con `cron.unschedule` |

### Hallazgos

- **`pg_cron` y `pg_net` no vienen activadas** en el proyecto: la primera llamada a `cron.schedule` falló con `schema "cron" does not exist`. Hay que activarlas (Database → Extensions) antes de programar nada. Solo `supabase_vault` estaba instalada.
- **El secreto debe ser idéntico en Vercel y en Vault**, sin comillas, espacios ni saltos de línea. Un valor distinto da `401` en `net._http_response`, el mismo síntoma que si falta el secreto en Vault. El arreglo fue generar un valor nuevo en SQL (`gen_random_uuid()` dos veces, 64 caracteres), ponerlo en Vercel, redesplegar y actualizar Vault.
- `vault.update_secret` no devuelve nada (la celda sale vacía); `vault.create_secret` devuelve el id.
- Ejecutar varias sentencias juntas en el SQL Editor de Supabase solo muestra el resultado de la última.
- Al definitivo (`/internal/jobs`, `/reminders`, `/cleanup`) le valen el mismo esquema de secreto en cabecera y la misma tarea de `pg_cron`.

**Conclusión (2026-10-23):** `pg_cron` llama cada minuto a la función de Vercel con `pg_net`, con el secreto guardado en Vault, y la llamada queda en `net._http_response` y en los registros de Vercel. La arquitectura del reloj es viable en el plan gratuito. La tarea se deja corriendo hasta el 2026-10-30 para ver si Supabase pausa el proyecto (C6).

### Limpieza diaria definitiva (`compabook-cleanup`)

Con el mismo esquema (secreto de Vault en `X-Internal-Secret`) se programó `POST /api/v1/internal/cleanup`.

| # | Resultado | Fecha | Notas |
|---|---|---|---|
| L1 | ✅ | 2026-10-23 | Llamada manual con `net.http_post`: reportada por Emile como «todo bien»; sin detalle del `content` |
| L2 | ✅ | 2026-10-23 | `cron.schedule('compabook-cleanup', '0 4 * * *', ...)`: una vez al día a las 04:00 UTC |
| L3 | Pendiente | | Comprobar en `cron.job_run_details` que corrió sola tras las 04:00 UTC (a partir del 2026-10-24) |

```sql
select cron.schedule(
  'compabook-cleanup',
  '0 4 * * *',
  $$
  select net.http_post(
    url     := 'https://compabook.vercel.app/api/v1/internal/cleanup',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'X-Internal-Secret', (select decrypted_secret from vault.decrypted_secrets where name = 'internal_secret')
    )
  );
  $$
);
```

Notas para decidir al terminar:
- Dejar la tarea unos días activa también ayuda a responder el pendiente «¿Supabase gratis pausa el proyecto por inactividad aunque `pg_cron` esté activo?». Son unas 1.440 llamadas al día; conviene mirar *Usage* en Vercel y en Supabase para confirmar que caben en el plan.
- El secreto en Vault solo lo ve quien tenga acceso al panel de Supabase. Para rotarlo: nuevo valor en Vercel, `vault.update_secret` y redeploy.
