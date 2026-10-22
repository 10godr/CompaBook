# Diseño técnico — CompaBook (MVP multiusuario)

> Fase 2 (replanteada el 2026-10-23). Define cómo se construye lo descrito en [`contexto.md`](contexto.md). Nada de esto está implementado todavía.

---

## 1. Servicios externos

### 1.1 PostgreSQL en Supabase

- Se usa **solo la base de datos** y la extensión **`pg_cron`** (+ `pg_net` para llamadas HTTP).
- **Supabase Auth no se usa.** La **Data API** (PostgREST) se desactiva en el panel, y RLS se activa en todas las tablas sin políticas, para que nada sea accesible salvo desde el backend.
- Conexión desde FastAPI: `DATABASE_URL` del **pooler en modo transacción** (puerto 6543) con `psycopg` 3. En este modo hay que desactivar los *prepared statements* (`prepare_threshold=None`) y usar `NullPool` en SQLAlchemy, porque cada invocación serverless abre y cierra su conexión.
- Migraciones con **Alembic** usando la conexión directa (puerto 5432) desde la computadora del desarrollador.

### 1.2 Gemini API (nivel gratuito)

Verificado en la documentación oficial (pricing actualizado el 2026-10-15). Los límites exactos se ven en [AI Studio → Rate limit](https://aistudio.google.com/rate-limit), son **por proyecto** y el cupo diario se reinicia a medianoche hora del Pacífico.

| Uso | Modelo | Variable |
|---|---|---|
| Principal | `gemini-3.8-flash` | `GEMINI_MODEL` |
| Respaldo (429 / cupo agotado) | `gemini-3.5-flash-lite` | `GEMINI_FALLBACK_MODEL` |

Salida estructurada (`response_mime_type: application/json` + `response_schema`) y validación con Pydantic antes de guardar.

### 1.3 YouTube Data API v3

- Cupo gratuito: **10.000 unidades/día** para todo el proyecto; `search.list` cuesta 100 → **~100 búsquedas/día en total**.
- Por eso se **reutilizan resultados** (`video_cache`, ver §3.3).
- Búsqueda: `q=<search_query que da Gemini>`, `relevanceLanguage=<es|en>`, `type=video`, `videoEmbeddable=true`, `safeSearch=moderate`, `maxResults=5`; se guardan los 2 primeros.

### 1.4 Correo: Gmail del proyecto

- SMTP `smtp.gmail.com:587` (STARTTLS) con **contraseña de aplicación** (requiere verificación en dos pasos en la cuenta).
- Límite aproximado de 500 destinatarios/día.
- Detrás de una interfaz `EmailProvider` con implementación `GmailSmtpProvider`; migrable a Resend cambiando la implementación.
- Plantillas en es/en: código de verificación y código de recuperación.

### 1.5 Vercel (Hobby)

- Un **único proyecto**: el frontend estático y el backend en `/api`, bajo el **mismo dominio** `*.vercel.app`.
- Esto es importante: con el mismo origen la cookie de sesión es *first-party*. Safari en iPhone bloquea cookies de terceros, y si frontend y backend estuvieran en dominios distintos el login fallaría.
- Cada invocación tiene un tiempo máximo; el tick procesa pocos trabajos por llamada (`TICK_MAX_JOBS`).

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

### 2.2 Contraseñas

- **argon2id** con `pwdlib`.
- Mínimo 8 caracteres; se rechazan contraseñas muy comunes.
- El login responde igual si el email no existe o la contraseña es incorrecta (no revela qué cuentas existen).

### 2.3 Códigos por email

- 6 dígitos, generados con `secrets`, guardados **hasheados**.
- Caducan a los **15 minutos**; máximo **5 intentos** por código.
- Un código nuevo invalida el anterior del mismo propósito.
- Máximo **5 envíos por hora** por email.

### 2.4 Protección contra abuso y CSRF

- Login: tras 5 fallos seguidos, la cuenta se bloquea 15 minutos (`failed_logins`, `locked_until`).
- CSRF: `SameSite=Lax` + el backend exige la cabecera `X-Requested-With: compabook` en todo `POST/PATCH/DELETE` con cookie. Un formulario de otro sitio no puede enviar esa cabecera.

### 2.5 Flujos

**Registro**
1. `POST /auth/register` `{ email, password, language, timezone }` → crea usuario con `email_verified_at = null` y envía código.
2. `POST /auth/verify-email` `{ email, code }` → marca verificado e inicia sesión.
3. Hasta verificar, no se puede iniciar sesión (se ofrece reenviar el código).

**Recuperar contraseña**
1. `POST /auth/forgot-password` `{ email }` → siempre responde 200; si existe, envía código.
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
  failed_logins     int not null default 0,
  locked_until      timestamptz,
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

concepts (
  id            uuid pk,
  user_id       uuid references users on delete cascade,
  title         text not null,       -- lo que escribió el usuario: «CI/CD»
  language      text not null,       -- idioma de la ficha (el del usuario al crearlo)
  source        text not null default 'app',   -- app | siri
  created_at    timestamptz
)

concept_cards (                      -- una ficha por concepto
  concept_id    uuid pk references concepts on delete cascade,
  canonical_title text not null,     -- nombre normalizado que devuelve la IA
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
  cache_key    text not null,        -- canonical_title normalizado + idioma
  language     text not null,
  position     smallint not null,    -- 1 | 2
  youtube_id   text not null,
  title        text not null,
  channel      text,
  thumbnail_url text not null,
  fetched_at   timestamptz,
  unique (cache_key, language, position)
)

processing_jobs (
  id           uuid pk,
  user_id      uuid references users on delete cascade,
  concept_id   uuid references concepts on delete cascade,
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

Índices: `concepts (user_id, created_at desc)`, `pg_trgm` sobre `concepts.title` para la búsqueda, `processing_jobs (status, next_run_at)`, `sessions (expires_at)`.

**Aislamiento entre usuarios:** los repositorios del backend (`ConceptRepository`, etc.) reciben siempre el `user_id` de la sesión y lo aplican en cada consulta. Nunca se acepta un `user_id` enviado por el cliente.

---

## 4. Procesamiento en segundo plano

### 4.1 El reloj

`pg_cron` ejecuta cada minuto:

```sql
select net.http_post(
  url     := 'https://<app>.vercel.app/api/v1/internal/tick',
  headers := jsonb_build_object('X-Tick-Secret', <secreto guardado en Supabase Vault>)
);
```

### 4.2 Qué hace `/internal/tick`

```
1. Toma hasta TICK_MAX_JOBS trabajos pending con next_run_at <= now()
   (UPDATE ... FOR UPDATE SKIP LOCKED → processing, locked_at = now())
2. Por cada trabajo:
   a. stage=writing          → Gemini (idioma del concepto) → valida → guarda concept_card
   b. stage=finding_videos   → video_cache por cache_key+idioma
                                 ├─ existe → reutiliza
                                 └─ no     → YouTube → guarda en video_cache
      Si YouTube falla, la ficha se muestra igual sin videos (no se marca failed).
   c. stage=done, status=completed
3. Si falla: attempts+1, last_error, next_run_at = now() + 2^attempts minutos;
   al llegar a max_attempts → failed
4. Trabajos processing con locked_at de hace más de 5 min → vuelven a pending
5. Recordatorios (§4.4)
6. Limpieza: sesiones y códigos caducados
```

### 4.3 Panel de carga

El frontend consulta `GET /concepts/{id}/status` cada 3 s mientras el trabajo esté activo y para al terminar.

| `status` | `stage` | es | en |
|---|---|---|---|
| `pending` | `queued` | En cola, ya casi le toca… | In line, almost there… |
| `processing` | `writing` | Escribiendo la explicación… | Writing the explanation… |
| `processing` | `finding_videos` | Buscando videos… | Finding videos… |
| `completed` | `done` | ¡Listo! | Done! |
| `failed` | — | No se pudo generar + **Reintentar** | Couldn't generate + **Retry** |

- Skeleton animado con la forma de la ficha y una barra de etapas.
- El concepto aparece en el Cuaderno desde el primer segundo con su estado.
- Se puede seguir usando la app mientras tanto.
- Respeta `prefers-reduced-motion`.

### 4.4 Recordatorios

En cada tick, para cada usuario con `enabled = true` y al menos una suscripción activa:

1. Calcular la fecha y hora **locales** con su `timezone`.
2. Enviar si: el día de la semana está en `weekdays`, la hora local ≥ `local_time`, y `last_sent_on` ≠ hoy (local).
3. Elegir un concepto al azar con ficha completada; si no hay ninguno, no enviar.
4. Mensaje (en su idioma): «Tienes 12 conceptos en tu Cuaderno — repasa "CI/CD"».
5. Guardar `last_sent_on = hoy`. Al tocar la notificación se abre `/concepts/{id}`.

Con esta lógica, si un tick se retrasa o falla, el siguiente envía el recordatorio igualmente y nunca se manda dos veces el mismo día.

---

## 5. Ficha generada por la IA

### 5.1 Prompt (resumen)

- Entrada: el texto del usuario (cualquier idioma) y `language`.
- Instrucción: responder **siempre en `language`**, breve, para alguien sin conocimientos previos, con un ejemplo concreto.
- No incluir URLs.

### 5.2 Esquema de respuesta

```json
{
  "canonical_title": "CI/CD (Continuous Integration / Continuous Delivery)",
  "what_is": "2–4 frases.",
  "what_for": "2–4 frases o una lista corta.",
  "example": "Un caso real explicado en pocas líneas.",
  "example_code": "opcional",
  "example_code_language": "opcional, p. ej. yaml",
  "youtube_search_query": "qué es CI/CD explicado"
}
```

- `canonical_title` normaliza variantes («ci cd», «CI/CD», «integración continua») y sirve para la `cache_key` de videos.
- `youtube_search_query` va en el idioma del usuario.

### 5.3 Videos en pantalla

- 2 tarjetas una al lado de la otra en escritorio y apiladas en móvil.
- Cada una: miniatura (`thumbnail_url`) y debajo el título; el canal en gris.
- Clic → `https://www.youtube.com/watch?v=<youtube_id>` en pestaña nueva (`target="_blank" rel="noopener"`).

---

## 6. Idioma de la interfaz (i18n)

- Librería: `react-i18next` con archivos `es.json` y `en.json`.
- **Sin sesión:** idioma del dispositivo (`navigator.language` empieza por `en` → inglés; en otro caso español), con selector visible para cambiarlo (se recuerda en `localStorage`).
- **Con sesión:** manda `users.language`.
- Los correos y las notificaciones usan `users.language`.

---

## 7. Contrato de API

Base `/api/v1`. Autenticación por cookie `cb_session`, salvo donde se indica. Errores: `{ "error": { "code": "...", "message": "..." } }`.

### Cuenta

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/auth/register` | `{ email, password, language, timezone }` → 201, envía código |
| `POST` | `/auth/verify-email` | `{ email, code }` → inicia sesión |
| `POST` | `/auth/resend-code` | `{ email, purpose }` |
| `POST` | `/auth/login` | `{ email, password }` → cookie |
| `POST` | `/auth/logout` | Cierra la sesión actual |
| `POST` | `/auth/forgot-password` | `{ email }` → siempre 200 |
| `POST` | `/auth/reset-password` | `{ email, code, new_password }` |
| `GET` | `/me` | Usuario actual |
| `PATCH` | `/me` | `{ language?, timezone? }` |
| `POST` | `/me/change-password` | `{ current_password, new_password }` |
| `DELETE` | `/me` | `{ password }` → elimina cuenta y datos |

### Cuaderno

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/concepts` | `{ title }` → 201 con `status` del trabajo |
| `GET` | `/concepts` | `q`, `limit`, `cursor`; orden por fecha descendente |
| `GET` | `/concepts/{id}` | Concepto + ficha + videos + estado |
| `GET` | `/concepts/{id}/status` | `{ status, stage, attempts }` para el polling |
| `POST` | `/concepts/{id}/retry` | Solo si `failed` → 202 |
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
| `POST` | `/siri/concepts` | Auth `Bearer <token>`. `{ text }` → 201 `{ message }` en el idioma del usuario |

### Interno

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/internal/tick` | Solo con `X-Tick-Secret` |
| `GET` | `/health` | Sin auth |

---

## 8. Variables de entorno

`backend/.env.example`

```
DATABASE_URL=postgresql+psycopg://...:6543/postgres      # pooler (app)
DATABASE_URL_DIRECT=postgresql+psycopg://...:5432/postgres  # Alembic
APP_URL=http://localhost:5173
COOKIE_SECURE=false
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
TICK_SECRET=
TICK_MAX_JOBS=3
```

`frontend/.env.example` (solo valores públicos)

```
VITE_API_URL=/api/v1
VITE_VAPID_PUBLIC_KEY=
```

En local, Vite reenvía `/api` al backend (`proxy`) para reproducir el mismo origen que en Vercel.

---

## 9. Textos legales

Borradores en es/en, publicados en `/legal/privacy`, `/legal/cookies` y `/legal/terms`, con enlace en el registro y en el pie de página.

- **Marco:** República Dominicana, **Ley 172-13** de protección de datos personales.
- **Responsable y contacto:** el Gmail del proyecto.
- **Privacidad:** datos recogidos (email, idioma, zona horaria, conceptos, suscripciones push); finalidad; proveedores (Supabase, Vercel, Google Gemini, YouTube, Gmail); aviso de que el nivel gratuito de Gemini puede usar el contenido para mejorar productos de Google; derechos de acceso, rectificación y eliminación (eliminar cuenta en Ajustes o escribir al contacto).
- **Cookies:** solo `cb_session` (estrictamente necesaria) y `localStorage` para el idioma antes de iniciar sesión. Sin analítica ni publicidad, así que no hace falta banner de consentimiento; basta un aviso informativo.
- **Términos:** uso personal y no comercial, contenido generado por IA que puede contener errores, servicio sin garantías durante las pruebas.
- Al registrarse, casilla obligatoria: «Acepto los términos y la política de privacidad».

---

## 10. Criterios de aceptación

**Fundamentos**
- [ ] `/health` responde en Vercel y conecta con la base de datos de Supabase.
- [ ] `alembic upgrade head` crea todas las tablas.
- [ ] La web abre en el idioma del dispositivo y se puede cambiar.

**Cuentas**
- [ ] Registro → llega el código al correo → cuenta verificada y sesión iniciada.
- [ ] Login, logout y recuperación de contraseña funcionan; recuperar cierra las otras sesiones.
- [ ] 5 fallos seguidos bloquean el login 15 minutos.
- [ ] Con dos cuentas, ninguna ve los conceptos de la otra (también probando IDs ajenos en la API).
- [ ] Eliminar la cuenta borra todos sus datos.
- [ ] El login funciona en Safari de iPhone con la PWA instalada.

**Cuaderno e IA**
- [ ] El concepto se guarda aunque Gemini esté caído.
- [ ] Un concepto escrito en inglés por un usuario en español genera la ficha en español, y viceversa.
- [ ] Mientras se genera se ve el panel de carga por etapas; la app no se congela.
- [ ] La ficha aparece sola, en menos de ~2 minutos en condiciones normales.
- [ ] Se muestran 2 videos con miniatura y título; el clic abre YouTube.
- [ ] Un segundo usuario que pide el mismo concepto en el mismo idioma reutiliza los videos (sin búsqueda nueva).
- [ ] Un fallo muestra **Reintentar** y funciona.
- [ ] Búsqueda y eliminación en el Cuaderno.

**Recordatorios**
- [ ] Elegir hora y días; la notificación llega en el iPhone (PWA instalada) con un margen de ±2 minutos.
- [ ] No llega en días no elegidos, ni dos veces el mismo día, ni con el Cuaderno vacío.
- [ ] Tocarla abre el concepto sugerido.

**Siri**
- [ ] Dictar un concepto lo crea y Siri confirma en el idioma del usuario.
- [ ] Un token revocado devuelve 401.

**Legal**
- [ ] Las tres páginas existen en es/en y están enlazadas en el registro y el pie de página.

---

## 11. Pendientes

- [ ] Anotar los límites reales de Gemini al crear la clave.
- [ ] Confirmar el tiempo máximo de función en Vercel Hobby en el primer despliegue y ajustar `TICK_MAX_JOBS`.
- [ ] Probar pronto que la PWA instalada en iPhone recibe push.
