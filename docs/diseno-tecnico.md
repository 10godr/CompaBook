# Diseño técnico — CompaBook (MVP multiusuario)

> Fase 2 (replanteada y revisada el 2026-10-22). Define cómo se construye lo descrito en [`contexto.md`](contexto.md), que manda si hay contradicción. Nada de esto está implementado todavía.

---

## 1. Servicios externos

### 1.1 PostgreSQL en Supabase

- Se usa **solo la base de datos** y la extensión **`pg_cron`** (+ `pg_net` para llamadas HTTP).
- **Supabase Auth no se usa.** La **Data API** (PostgREST) se desactiva en el panel, y RLS se activa en todas las tablas sin políticas, para que nada sea accesible salvo desde el backend.
- Conexión desde FastAPI: `DATABASE_URL` del **pooler en modo transacción** (puerto 6543) con `psycopg` 3. En este modo hay que desactivar los *prepared statements* (`prepare_threshold=None`) y usar `NullPool` en SQLAlchemy, porque cada invocación serverless abre y cierra su conexión.
- Migraciones con **Alembic** usando la conexión directa (puerto 5432).
- Dos proyectos: **`compabook-dev`** (previews de Vercel) y **`compabook-prod`** (producción, el único con `pg_cron`). Ver §8.
- Por verificar en el plan gratuito: si el proyecto se **pausa** por inactividad y qué **copias de seguridad** incluye. Si no hay copias, `pg_dump` semanal guardado fuera de Supabase.

### 1.2 Gemini API (nivel gratuito)

Verificado en la documentación oficial (pricing actualizado el 2026-10-15). Los límites exactos se ven en [AI Studio → Rate limit](https://aistudio.google.com/rate-limit), son **por proyecto** y el cupo diario se reinicia a medianoche hora del Pacífico.

| Uso | Modelo | Variable |
|---|---|---|
| Principal | `gemini-3.8-flash` | `GEMINI_MODEL` |
| Respaldo (429 / cupo agotado) | `gemini-3.5-flash-lite` | `GEMINI_FALLBACK_MODEL` |

Salida estructurada (`response_mime_type: application/json` + `response_schema`) y validación con Pydantic antes de guardar.

### 1.3 YouTube Data API v3

- Cupo gratuito: **10.000 unidades/día** para todo el proyecto; `search.list` cuesta 100 → **~100 búsquedas/día en total**.
- Por eso se **reutilizan resultados** (`video_cache`, ver §3) y existe el límite diario por usuario (§2.5).
- Búsqueda: `q=<youtube_search_query que da Gemini>`, `relevanceLanguage=<es|en>`, `type=video`, `videoEmbeddable=true`, `safeSearch=moderate`, `maxResults=5`; se guardan los 2 primeros.

### 1.4 Correo: Gmail del proyecto

- SMTP `smtp.gmail.com:587` (STARTTLS) con **contraseña de aplicación** (requiere verificación en dos pasos en la cuenta).
- Límite aproximado de 500 destinatarios/día.
- Detrás de una interfaz `EmailProvider` con implementación `GmailSmtpProvider`; migrable a Resend cambiando la implementación.
- Plantillas en es/en: código de verificación, código de recuperación y aviso de «ya tienes cuenta» (§2.5).
- Riesgo conocido: los correos pueden llegar a **spam**. Las pantallas de código lo avisan y ofrecen reenviar.
- Tiempo máximo de conexión SMTP de 10 s para no dejar colgada la petición de registro.

### 1.5 Vercel (Hobby)

- Un **único proyecto**: el frontend estático y el backend en `/api`, bajo el **mismo dominio** `*.vercel.app`.
- Esto es importante: con el mismo origen la cookie de sesión es *first-party*. Safari en iPhone bloquea cookies de terceros, y si frontend y backend estuvieran en dominios distintos el login fallaría.
- Cada invocación tiene un tiempo máximo; `/internal/jobs` procesa pocos trabajos por llamada (`JOBS_MAX_PER_RUN`) y la generación al momento procesa uno solo.
- Cada PR genera un **preview** con su propia URL, conectado a `compabook-dev`.

### 1.6 Web Push

- Claves **VAPID**; la pública va al frontend y la privada solo al backend.
- Envío con `pywebpush`. Si un envío devuelve 404/410, la suscripción se marca inactiva.

---

## 2. Autenticación (login propio)

### 2.1 Decisión: sesiones en base de datos

En lugar de JWT se usan **tokens de sesión opacos** guardados en la base de datos. Para este proyecto son más simples y más seguros:

- Cerrar sesión o eliminar la cuenta invalida la sesión al instante (con JWT habría que esperar a que caduque).
- No hay claves de firma que gestionar ni rotar.
- El coste (una consulta por petición) es irrelevante a esta escala.

Funcionamiento:

1. Al iniciar sesión se genera un token aleatorio (`secrets.token_urlsafe(32)`).
2. En la base de datos se guarda **su hash SHA-256**, no el token.
3. El token va al navegador en la cookie `cb_session`: `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, 30 días.
4. En cada petición se hashea la cookie y se busca la sesión vigente.
5. **Renovación deslizante:** si `last_used_at` tiene más de 24 h, se actualiza y `expires_at` pasa a ahora + 30 días (y se reenvía la cookie). Quien usa la app no tiene que volver a entrar; una sesión sin uso caduca a los 30 días.

### 2.2 Contraseñas

- **argon2id** con `pwdlib`.
- Mínimo 8 caracteres y máximo 128; se rechazan contraseñas muy comunes.
- El login responde igual si el email no existe o la contraseña es incorrecta (no revela qué cuentas existen).

### 2.3 Códigos por email

- 6 dígitos, generados con `secrets`, guardados **hasheados**.
- Caducan a los **15 minutos**; máximo **5 intentos** por código.
- Un código nuevo invalida el anterior del mismo propósito.
- Máximo **5 envíos por hora** por email.

### 2.4 Límites de intentos y CSRF

Los límites se guardan en `rate_limit_events` (§3): cada intento añade una fila y se cuentan las de la ventana. Así funciona en serverless sin memoria compartida.

| Acción | Clave | Límite |
|---|---|---|
| Login fallido | email + IP | 5 en 15 min → se responde `429` con `retry_after`; la espera se duplica en cada bloqueo siguiente (máx. 1 h) |
| Login (cualquier resultado) | IP | 30 por hora |
| Registro | IP | 10 por hora |
| Envío de códigos | email | 5 por hora |
| Crear concepto | usuario | `DAILY_CONCEPT_LIMIT` al día |
| Reintentar | usuario | `DAILY_RETRY_LIMIT` al día |
| Siri | token | 30 por hora |

- **No se bloquea la cuenta.** El límite es por email + IP, así que un atacante no puede dejar fuera al dueño desde otra red.
- La IP se toma de la cabecera `x-forwarded-for` que pone Vercel (primer valor).
- **CSRF:** `SameSite=Lax` + el backend exige la cabecera `X-Requested-With: compabook` en todo `POST/PUT/PATCH/DELETE` con cookie. Un formulario de otro sitio no puede enviar esa cabecera.

### 2.5 Flujos

**Registro**
1. `POST /auth/register` `{ email, password, language, timezone, accept_terms }` → **siempre 202** con el mismo mensaje («Si el email es válido, te enviamos un código»).
   - Email nuevo: crea usuario con `email_verified_at = null` y envía código.
   - Email ya registrado: no cambia nada y envía un correo «Ya tienes una cuenta; ¿olvidaste tu contraseña?». Así el registro no revela qué emails existen.
2. `POST /auth/verify-email` `{ email, code }` → marca verificado e inicia sesión.
3. Hasta verificar, no se puede iniciar sesión (se ofrece reenviar el código).
4. Las cuentas sin verificar se borran a los 7 días (`/internal/cleanup`).

**Recuperar contraseña**
1. `POST /auth/forgot-password` `{ email }` → siempre 200; si existe, envía código.
2. `POST /auth/reset-password` `{ email, code, new_password }` → cambia la contraseña y **cierra todas las sesiones**.

**Eliminar cuenta**
- `DELETE /me` `{ password }` → borra el usuario y en cascada todos sus datos; borra la cookie.

---

## 3. Modelo de datos

Todas las tablas usan `id uuid` y `timestamptz` en UTC. Se definen como modelos de SQLAlchemy 2.0 (`Mapped[...]`) y se crean con Alembic.

```sql
users (
  id                uuid pk,
  email             citext unique not null,
  password_hash     text not null,
  language          text not null check (language in ('es','en')),
  timezone          text not null,              -- p. ej. 'America/Santo_Domingo'
  email_verified_at timestamptz,
  created_at, updated_at timestamptz
)

sessions (
  id           uuid pk,
  user_id      uuid references users on delete cascade,
  token_hash   text unique not null,
  user_agent   text,
  expires_at   timestamptz not null,
  last_used_at timestamptz,
  created_at   timestamptz
)

email_codes (
  id         uuid pk,
  user_id    uuid references users on delete cascade,
  purpose    text not null,          -- verify_email | reset_password
  code_hash  text not null,
  attempts   int not null default 0,
  expires_at timestamptz not null,
  used_at    timestamptz,
  created_at timestamptz
)

rate_limit_events (
  id         bigint generated always as identity pk,
  bucket     text not null,          -- login_fail | login_ip | register_ip | email_send | concept_create | retry | siri
  key        text not null,          -- email+ip, ip, email, user_id o token_id según el bucket
  created_at timestamptz not null default now()
)

concepts (
  id            uuid pk,
  user_id       uuid references users on delete cascade,
  title         text not null check (char_length(title) between 1 and 200),  -- lo que escribió el usuario: «CI/CD»
  language      text not null,       -- idioma de la ficha (el del usuario al crearlo)
  source        text not null default 'app',   -- app | siri
  created_at    timestamptz
)

concept_cards (                      -- una ficha por concepto
  concept_id    uuid pk references concepts on delete cascade,
  canonical_title text not null,     -- nombre para mostrar que devuelve la IA
  cache_slug    text not null,       -- clave estable para la caché de videos: 'ci-cd'
  what_is       text not null,
  what_for      text not null,
  example       text not null,
  example_code  text,
  example_code_language text,
  model         text not null,
  created_at    timestamptz
)

video_cache (                        -- compartida entre usuarios
  id           uuid pk,
  cache_slug   text not null,
  language     text not null,
  position     smallint not null,    -- 1 | 2
  youtube_id   text not null,
  title        text not null,
  channel      text,
  thumbnail_url text not null,
  fetched_at   timestamptz,
  unique (cache_slug, language, position)
)

processing_jobs (                    -- un trabajo por concepto
  id           uuid pk,
  user_id      uuid references users on delete cascade,
  concept_id   uuid unique references concepts on delete cascade,
  status       text not null default 'pending',  -- pending | processing | completed | failed
  stage        text not null default 'queued',   -- queued | writing | finding_videos | done
  attempts     int not null default 0,
  max_attempts int not null default 3,
  next_run_at  timestamptz default now(),
  locked_at    timestamptz,
  last_error   text,
  created_at, updated_at timestamptz
)

reminder_settings (
  user_id      uuid pk references users on delete cascade,
  enabled      boolean not null default false,
  local_time   time not null default '20:00',
  weekdays     smallint[] not null default '{1,2,3,4,5,6,7}',  -- ISO: 1=lunes … 7=domingo
  last_sent_on date,                 -- fecha local del último envío (evita duplicados)
  updated_at   timestamptz
)

push_subscriptions (
  id         uuid pk,
  user_id    uuid references users on delete cascade,
  endpoint   text unique not null,
  p256dh     text not null,
  auth       text not null,
  user_agent text,
  active     boolean not null default true,
  created_at timestamptz
)

api_tokens (                         -- atajo de Siri
  id           uuid pk,
  user_id      uuid references users on delete cascade,
  name         text,
  token_hash   text unique not null,
  last_used_at timestamptz,
  revoked_at   timestamptz,
  created_at   timestamptz
)
```

Índices: `concepts (user_id, created_at desc)`, `pg_trgm` sobre `concepts.title` para la búsqueda, `processing_jobs (status, next_run_at)`, `sessions (expires_at)`, `rate_limit_events (bucket, key, created_at)`.

La zona horaria vive solo en `users.timezone`; los recordatorios la leen de ahí.

**Aislamiento entre usuarios:** los repositorios del backend (`ConceptRepository`, etc.) reciben siempre el `user_id` de la sesión y lo aplican en cada consulta. Nunca se acepta un `user_id` enviado por el cliente. Un test automático lo comprueba (§9).

---

## 4. Procesamiento

### 4.1 Generación al momento

1. `POST /concepts` guarda el concepto y su trabajo (`pending`) en una transacción y responde 201.
2. El frontend llama enseguida a `POST /concepts/{id}/process`.
3. Ese endpoint **reclama** el trabajo (`UPDATE ... WHERE status='pending' ... FOR UPDATE SKIP LOCKED`) y ejecuta los pasos de §4.3 en la misma petición. Si otro proceso ya lo tiene, responde 202 sin hacer nada.
4. Mientras tanto, el frontend consulta el estado (§4.5).

Si la pestaña se cierra o la petición se corta, el trabajo sigue `pending` o queda `processing` con `locked_at` antiguo, y el reloj lo recoge.

### 4.2 El reloj

`pg_cron` (solo en `compabook-prod`) llama a tres endpoints internos:

| Tarea | Frecuencia | Endpoint |
|---|---|---|
| Trabajos pendientes y reintentos | cada minuto | `/api/v1/internal/jobs` |
| Recordatorios | cada minuto | `/api/v1/internal/reminders` |
| Limpieza | una vez al día (04:00 UTC) | `/api/v1/internal/cleanup` |

```sql
select net.http_post(
  url     := 'https://<app>.vercel.app/api/v1/internal/jobs',
  headers := jsonb_build_object('X-Internal-Secret', <secreto guardado en Supabase Vault>)
);
```

Separarlas evita que una llamada lenta a Gemini retrase los recordatorios o corte la función por tiempo.

### 4.3 Procesar un trabajo

```
1. stage=writing         → solo si el concepto aún no tiene concept_card:
                           Gemini (idioma del concepto) → valida → guarda concept_card
2. stage=finding_videos  → video_cache por cache_slug + idioma
                             ├─ existe → reutiliza
                             └─ no     → YouTube → guarda en video_cache
   Si YouTube falla, la ficha se muestra igual sin videos (no se marca failed).
3. stage=done, status=completed
Si falla el paso 1: attempts+1, last_error, next_run_at = now() + 2^attempts minutos;
al llegar a max_attempts → failed
```

### 4.4 `/internal/jobs` y `/internal/cleanup`

- **jobs:** toma hasta `JOBS_MAX_PER_RUN` trabajos `pending` con `next_run_at <= now()` y los procesa; los `processing` con `locked_at` de hace más de 5 min vuelven a `pending`.
- **cleanup:** borra sesiones caducadas, códigos caducados, `rate_limit_events` de más de 2 días y cuentas sin verificar de más de 7 días.

**Reintentar** (`POST /concepts/{id}/retry`): solo si `failed`. Reinicia el **mismo** trabajo (`status=pending`, `attempts=0`, `next_run_at=now()`) y el frontend llama a `/process` como al crearlo. Como el paso 1 se salta si ya hay ficha, reintentar nunca gasta Gemini de más.

### 4.5 Panel de carga

El frontend consulta `GET /concepts/{id}/status` cada 2 s mientras el trabajo esté activo y para al terminar (o tras 3 minutos, mostrando «Sigue en cola, te avisamos al volver»).

| `status` | `stage` | es | en |
|---|---|---|---|
| `pending` | `queued` | En cola, ya casi le toca… | In line, almost there… |
| `processing` | `writing` | Escribiendo la explicación… | Writing the explanation… |
| `processing` | `finding_videos` | Buscando videos… | Finding videos… |
| `completed` | `done` | ¡Listo! | Done! |
| `failed` | — | No se pudo generar + **Reintentar** | Couldn't generate + **Retry** |

- Skeleton animado con la forma de la ficha y una barra de etapas (ver [`design.md`](design.md)).
- El concepto aparece en el Cuaderno desde el primer segundo con su estado.
- Se puede seguir usando la app mientras tanto.
- Respeta `prefers-reduced-motion`.

### 4.6 Recordatorios

En cada ejecución de `/internal/reminders`, la consulta selecciona solo usuarios con `enabled = true` y al menos una suscripción activa. Para cada uno:

1. Calcular la fecha y hora **locales** con `users.timezone`.
2. Enviar si: el día de la semana está en `weekdays`, la hora local está entre `local_time` y `local_time + 2 h`, y `last_sent_on` ≠ hoy (local).
3. Elegir un concepto al azar con ficha completada; si no hay ninguno, no enviar.
4. Mensaje (en su idioma): «Tienes 12 conceptos en tu Cuaderno — repasa "CI/CD"».
5. Guardar `last_sent_on = hoy`. Al tocar la notificación se abre `/concepts/{id}`.

Con esta lógica, si una ejecución se retrasa o falla, la siguiente envía el recordatorio igualmente y nunca se manda dos veces el mismo día. La ventana de 2 h evita avisos a deshora tras una caída larga, o al activar el recordatorio cuando su hora ya pasó.

---

## 5. Ficha generada por la IA

### 5.1 Prompt (resumen)

- Entrada: el texto del usuario (cualquier idioma, máximo 200 caracteres) y `language`.
- El texto del usuario va **delimitado** y marcado como dato, no como instrucción.
- Instrucción: responder **siempre en `language`**, breve, para alguien sin conocimientos previos, con un ejemplo concreto.
- No incluir URLs ni HTML.

### 5.2 Esquema de respuesta

```json
{
  "canonical_title": "CI/CD (Continuous Integration / Continuous Delivery)",
  "cache_slug": "ci-cd",
  "what_is": "2–4 frases.",
  "what_for": "2–4 frases o una lista corta.",
  "example": "Un caso real explicado en pocas líneas.",
  "example_code": "opcional",
  "example_code_language": "opcional, p. ej. yaml",
  "youtube_search_query": "qué es CI/CD explicado"
}
```

- `canonical_title` es el nombre bonito para mostrar.
- `cache_slug` es la clave de la caché de videos: **siempre en inglés, minúsculas, palabras separadas por guiones, sin paréntesis ni siglas expandidas**. Variantes como «ci cd», «CI/CD» o «integración continua» deben dar el mismo `ci-cd`. El backend lo vuelve a normalizar (minúsculas, `[a-z0-9-]`, máximo 60 caracteres) antes de usarlo.
- `youtube_search_query` va en el idioma del usuario.

### 5.3 Mostrar la ficha

- Todo se pinta como **texto** con React (sin `dangerouslySetInnerHTML`). Los saltos de línea se respetan con CSS.
- `example_code` va en un bloque `<pre><code>` con fuente monoespaciada; sin resaltado de sintaxis en el MVP.

### 5.4 Videos en pantalla

- 2 tarjetas una al lado de la otra en escritorio y apiladas en móvil.
- Cada una: miniatura (`thumbnail_url`) y debajo el título; el canal en gris.
- Clic → `https://www.youtube.com/watch?v=<youtube_id>` en pestaña nueva (`target="_blank" rel="noopener"`).

---

## 6. Idioma de la interfaz (i18n)

- Librería: `react-i18next` con archivos `es.json` y `en.json`.
- **Sin sesión:** idioma del dispositivo (`navigator.language` empieza por `en` → inglés; en otro caso español), con selector visible para cambiarlo (se recuerda en `localStorage`).
- **Con sesión:** manda `users.language`.
- Los correos, las notificaciones y las respuestas a Siri usan `users.language`.

---

## 7. Contrato de API

Base `/api/v1`. Autenticación por cookie `cb_session`, salvo donde se indica. Errores: `{ "error": { "code": "...", "message": "..." } }`.

Códigos de error comunes: `validation_error` (422), `unauthorized` (401), `not_found` (404, también para recursos de otro usuario), `rate_limited` (429, con `retry_after` en segundos), `daily_limit_reached` (429).

### Cuenta

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/auth/register` | `{ email, password, language, timezone, accept_terms }` → siempre 202 |
| `POST` | `/auth/verify-email` | `{ email, code }` → inicia sesión |
| `POST` | `/auth/resend-code` | `{ email, purpose }` → siempre 202 |
| `POST` | `/auth/login` | `{ email, password }` → cookie |
| `POST` | `/auth/logout` | Cierra la sesión actual |
| `POST` | `/auth/forgot-password` | `{ email }` → siempre 200 |
| `POST` | `/auth/reset-password` | `{ email, code, new_password }` |
| `GET` | `/me` | Usuario actual + uso del día (`concepts_today`, `daily_limit`) |
| `PATCH` | `/me` | `{ language?, timezone? }` |
| `POST` | `/me/change-password` | `{ current_password, new_password }` |
| `DELETE` | `/me` | `{ password }` → elimina cuenta y datos |

### Cuaderno

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/concepts` | `{ title }` (1–200 caracteres) → 201 con `id` y `status`; 429 `daily_limit_reached` |
| `POST` | `/concepts/{id}/process` | Genera la ficha al momento → 200 con el estado final, o 202 si ya la procesa otro |
| `GET` | `/concepts` | `q`, `limit`, `cursor`; orden por fecha descendente |
| `GET` | `/concepts/{id}` | Concepto + ficha + videos + estado |
| `GET` | `/concepts/{id}/status` | `{ status, stage, attempts }` para el polling |
| `POST` | `/concepts/{id}/retry` | Solo si `failed` → 202; 429 `daily_limit_reached` |
| `DELETE` | `/concepts/{id}` | Eliminar |

### Recordatorios y notificaciones

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/reminders` | Ajustes actuales |
| `PUT` | `/reminders` | `{ enabled, local_time, weekdays[] }` |
| `GET` | `/push/vapid-public-key` | Sin auth |
| `POST` | `/push/subscriptions` | `{ endpoint, keys: { p256dh, auth } }` |
| `DELETE` | `/push/subscriptions` | `{ endpoint }` |
| `POST` | `/push/test` | Notificación de prueba |

### Siri

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/tokens` | Crea token → se muestra **una sola vez** |
| `GET` | `/tokens` | Lista (sin el valor) |
| `DELETE` | `/tokens/{id}` | Revoca |
| `POST` | `/siri/concepts` | Auth `Bearer <token>`. `{ text }` → 201 `{ message }` en el idioma del usuario. La ficha la genera el reloj (Siri no espera) |

### Interno

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/internal/jobs` | Solo con `X-Internal-Secret` |
| `POST` | `/internal/reminders` | Solo con `X-Internal-Secret` |
| `POST` | `/internal/cleanup` | Solo con `X-Internal-Secret` |
| `GET` | `/health` | Sin auth; comprueba la conexión a la base de datos |

---

## 8. Entornos y variables

### 8.1 Entornos

| Entorno | Frontend + API | Base de datos | `pg_cron` |
|---|---|---|---|
| Local | Vite (`5173`) con proxy `/api` → Uvicorn (`8000`) | PostgreSQL 16 en Docker (`docker-compose.yml`) | No: se llama a `/internal/*` a mano o con un script |
| Preview | URL de Vercel por PR | Supabase `compabook-dev` | No |
| Producción | `<app>.vercel.app` | Supabase `compabook-prod` | Sí |

Las variables de cada entorno se configuran en Vercel por separado (*Preview* y *Production*). Las claves de Gemini y YouTube pueden compartirse al principio, sabiendo que comparten cuota.

### 8.2 Variables

`backend/.env.example`

```
DATABASE_URL=postgresql+psycopg://compabook:compabook@localhost:5432/compabook          # app (en Vercel: pooler 6543)
DATABASE_URL_DIRECT=postgresql+psycopg://compabook:compabook@localhost:5432/compabook   # Alembic (en Supabase: 5432)
APP_URL=http://localhost:5173
COOKIE_SECURE=false
SESSION_DAYS=30
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.8-flash
GEMINI_FALLBACK_MODEL=gemini-3.5-flash-lite
YOUTUBE_API_KEY=
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_APP_PASSWORD=
EMAIL_FROM_NAME=CompaBook
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
VAPID_SUBJECT=mailto:<gmail del proyecto>
INTERNAL_SECRET=
JOBS_MAX_PER_RUN=3
DAILY_CONCEPT_LIMIT=30
DAILY_RETRY_LIMIT=10
CONCEPT_TITLE_MAX=200
LOG_LEVEL=INFO
```

`frontend/.env.example` (solo valores públicos)

```
VITE_API_URL=/api/v1
VITE_VAPID_PUBLIC_KEY=
```

En local, Vite reenvía `/api` al backend (`proxy`) para reproducir el mismo origen que en Vercel. Sin `SMTP_USER`, el backend usa un `ConsoleEmailProvider` que escribe los códigos en la consola.

---

## 9. Calidad y observabilidad

### 9.1 CI (GitHub Actions)

Se ejecuta en cada PR y en cada push a `main`:

| Parte | Pasos |
|---|---|
| Backend | `ruff check`, `ruff format --check`, `alembic upgrade head` y `pytest` contra un PostgreSQL de servicio |
| Frontend | `eslint`, `tsc --noEmit`, `vite build` |

### 9.2 Tests mínimos del backend

- **Aislamiento:** con dos usuarios, cada endpoint de `/concepts`, `/reminders`, `/push` y `/tokens` devuelve 404 al pedir recursos del otro.
- Registro, verificación, login, recuperación y límites de intentos.
- Cola: reclamar un trabajo dos veces solo lo procesa una; reintentar no vuelve a llamar a Gemini si ya hay ficha.
- Recordatorios: día no elegido, fuera de la ventana, ya enviado hoy y Cuaderno vacío no envían.
- Gemini, YouTube, SMTP y Push se sustituyen por implementaciones falsas (`FakeAIProvider`, etc.).

### 9.3 Logs

- Logs en JSON a la salida estándar (los recoge Vercel) con `request_id`, `user_id` (si hay sesión) y `job_id` cuando aplica.
- Nunca se registran contraseñas, códigos, tokens, cookies ni el contenido de los conceptos.
- Los errores de los trabajos quedan además en `processing_jobs.last_error`.

---

## 10. Textos legales

Borradores en es/en, publicados en `/legal/privacy`, `/legal/cookies` y `/legal/terms`, con enlace en el registro y en el pie de página.

- **Marco:** República Dominicana, **Ley 172-13** de protección de datos personales.
- **Responsable y contacto:** el Gmail del proyecto.
- **Privacidad:** datos recogidos (email, idioma, zona horaria, conceptos, suscripciones push, IP para limitar intentos durante 2 días); finalidad; proveedores (Supabase, Vercel, Google Gemini, YouTube, Gmail); aviso de que el nivel gratuito de Gemini puede usar el contenido para mejorar productos de Google; derechos de acceso, rectificación y eliminación (eliminar cuenta en Ajustes o escribir al contacto).
- **Cookies:** solo `cb_session` (estrictamente necesaria) y `localStorage` para el idioma y el tema antes de iniciar sesión. Sin analítica ni publicidad, así que no hace falta banner de consentimiento; basta un aviso informativo.
- **Términos:** uso personal y no comercial, límite diario de uso, contenido generado por IA que puede contener errores, servicio sin garantías durante las pruebas.
- Al registrarse, casilla obligatoria: «Acepto los términos y la política de privacidad».

---

## 11. Criterios de aceptación

**Fundamentos y prueba de riesgos**
- [ ] `docker compose up` + `alembic upgrade head` crean todas las tablas en local.
- [ ] El CI corre en un PR y falla si falla un test.
- [ ] `/health` responde en Vercel (preview y producción) y conecta con su base de datos.
- [ ] Prueba de concepto: una cookie puesta por `/api` sobrevive en Safari con la PWA instalada en iPhone.
- [ ] Prueba de concepto: el backend envía un push que llega al iPhone con la PWA instalada.
- [ ] Prueba de concepto: `pg_cron` llama a `/internal/jobs` en producción y queda en los logs.
- [ ] La web abre en el idioma del dispositivo y se puede cambiar; el tema sigue al del sistema.

**Cuentas**
- [ ] Registro → llega el código al correo → cuenta verificada y sesión iniciada.
- [ ] Registrar un email ya existente responde igual que uno nuevo.
- [ ] Login, logout y recuperación de contraseña funcionan; recuperar cierra las otras sesiones.
- [ ] 5 fallos seguidos desde una IP fuerzan una espera, pero el dueño puede entrar desde otra red.
- [ ] El test automático de aislamiento pasa en el CI.
- [ ] Eliminar la cuenta borra todos sus datos.
- [ ] El login funciona en Safari de iPhone con la PWA instalada.

**Cuaderno e IA**
- [ ] El concepto se guarda aunque Gemini esté caído.
- [ ] Un concepto escrito en inglés por un usuario en español genera la ficha en español, y viceversa.
- [ ] La ficha empieza a generarse en el momento: «En cola» dura menos de 5 s en condiciones normales.
- [ ] Mientras se genera se ve el panel de carga por etapas; la app no se congela.
- [ ] Si se cierra la pestaña a mitad, la ficha se completa igualmente gracias al reloj.
- [ ] Se muestran 2 videos con miniatura y título; el clic abre YouTube.
- [ ] Un segundo usuario que pide el mismo concepto (aunque lo escriba distinto) en el mismo idioma reutiliza los videos.
- [ ] Un fallo muestra **Reintentar** y funciona; si la ficha ya existía, no se llama a Gemini.
- [ ] Al llegar al límite diario se muestra un mensaje claro y no se crea el concepto.
- [ ] Búsqueda y eliminación en el Cuaderno.

**Recordatorios**
- [ ] Elegir hora y días; la notificación llega en el iPhone (PWA instalada) con un margen de ±2 minutos.
- [ ] No llega en días no elegidos, ni dos veces el mismo día, ni con el Cuaderno vacío, ni fuera de la ventana de 2 h.
- [ ] Tocarla abre el concepto sugerido.

**Siri**
- [ ] Dictar un concepto lo crea y Siri confirma en el idioma del usuario.
- [ ] Un token revocado devuelve 401.

**Legal**
- [ ] Las tres páginas existen en es/en y están enlazadas en el registro y el pie de página.

---

## 12. Pendientes

- [ ] Anotar los límites reales de Gemini al crear la clave y ajustar `DAILY_CONCEPT_LIMIT`.
- [ ] Confirmar el tiempo máximo de función en Vercel Hobby en el primer despliegue y ajustar `JOBS_MAX_PER_RUN`.
- [ ] Verificar la pausa por inactividad y las copias de seguridad del plan gratuito de Supabase.
