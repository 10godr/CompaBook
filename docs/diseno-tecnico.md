# Diseño técnico — Knowledge Hub (MVP)

> Fase 2. Define cómo se construye lo descrito en [`contexto.md`](contexto.md). Nada de esto está implementado todavía.
> Última revisión: 2026-10-22.

---

## 1. Servicios externos

### 1.1 Gemini API (nivel gratuito)

Verificado en la documentación oficial (pricing actualizado el 2026-10-15):

- Modelos de texto con nivel gratuito: `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-2.5-pro`, `gemini-2.5-flash`, entre otros.
- Los límites (RPM / RPD) **no se publican en la documentación**: dependen del proyecto y se consultan en [AI Studio → Rate limit](https://aistudio.google.com/rate-limit). Son **por proyecto**, no por clave, y el cupo diario se reinicia a medianoche hora del Pacífico.
- En el nivel gratuito **Google puede usar el contenido para mejorar sus productos**.

**Decisión:**

| Uso | Modelo | Variable |
|---|---|---|
| Principal | `gemini-3.8-flash` | `GEMINI_MODEL` |
| Respaldo si hay 429 o cupo agotado | `gemini-3.5-flash-lite` | `GEMINI_FALLBACK_MODEL` |

Los modelos van en variables de entorno para cambiarlos sin tocar código. Se usa **salida estructurada** (`response_mime_type: application/json` + `response_schema`), y la respuesta se valida igualmente con Pydantic antes de guardar.

Al crear la clave, revisar en AI Studio los límites reales y anotarlos aquí.

### 1.2 YouTube Data API v3

- Cupo gratuito por defecto: **10.000 unidades/día**. `search.list` cuesta **100 unidades** → ~100 búsquedas/día; sobra para uso personal.
- Una búsqueda por concepto: `q=<título> explicación`, `relevanceLanguage=es`, `type=video`, `maxResults=5`, `safeSearch=moderate`.
- Se guardan hasta 3 videos. Si la API falla, la ficha se completa igual y los videos se reintentan aparte.

### 1.3 Supabase

- **Auth:** email + contraseña (o enlace mágico). El frontend obtiene un JWT.
- **Postgres + RLS** en todas las tablas.
- **`pg_cron` + `pg_net`:** cada minuto hace `POST https://<backend>/internal/tick` con la cabecera `X-Tick-Secret`.

### 1.4 Vercel (Hobby)

- Frontend: build estático de Vite.
- Backend: FastAPI como función serverless de Python.
- Cada invocación tiene un tiempo máximo; el tick procesa **pocos jobs por llamada** (`TICK_MAX_JOBS`, por defecto 3) para no pasarse.

### 1.5 Web Push

- Claves **VAPID** generadas una sola vez; la pública va al frontend y la privada solo al backend.
- Envío con la librería `pywebpush`.

---

## 2. Modelo de datos (PostgreSQL)

Todas las tablas tienen `user_id uuid references auth.users` y RLS `user_id = auth.uid()`. Timestamps en UTC (`timestamptz`).

```sql
-- Perfil (Supabase ya gestiona auth.users)
profiles (
  user_id     uuid primary key references auth.users on delete cascade,
  display_name text,
  timezone    text not null default 'America/Bogota',
  created_at  timestamptz default now()
)

categories (
  id uuid pk, user_id uuid, name text not null,
  unique (user_id, name)
)

concepts (
  id             uuid pk,
  user_id        uuid not null,
  title          text not null,             -- «CI/CD»
  original_text  text,                      -- lo que se dictó/escribió tal cual
  category_id    uuid references categories on delete set null,
  tags           text[] default '{}',
  learning_status text not null default 'new'   -- new | learning | learned
  source         text not null default 'app',   -- app | siri
  created_at, updated_at timestamptz
)

concept_content (                          -- ficha versionada
  id          uuid pk,
  concept_id  uuid references concepts on delete cascade,
  user_id     uuid,
  version     int not null,
  content     jsonb not null,               -- ver §4
  model       text not null,                -- modelo que la generó
  created_at  timestamptz,
  unique (concept_id, version)
)

concept_resources (
  id uuid pk, concept_id uuid, user_id uuid,
  youtube_id text not null, title text, channel text,
  url text not null, language text, thumbnail_url text,
  unique (concept_id, youtube_id)
)

processing_jobs (
  id           uuid pk,
  user_id      uuid,
  concept_id   uuid references concepts on delete cascade,
  type         text not null,               -- generate_content | fetch_videos
  status       text not null default 'pending',  -- pending | processing | completed | failed
  stage        text,                        -- para el panel de carga, ver §3.2
  attempts     int not null default 0,
  max_attempts int not null default 3,
  next_run_at  timestamptz default now(),   -- backoff de reintentos
  locked_at    timestamptz,                 -- evita que dos ticks tomen el mismo job
  last_error   text,
  created_at, updated_at timestamptz
)

study_sessions (
  id uuid pk, user_id uuid,
  title       text,
  scheduled_at timestamptz not null,        -- en UTC
  timezone    text not null,                -- zona con la que se creó
  status      text not null default 'scheduled', -- scheduled | notified | done | cancelled
  notified_at timestamptz,
  created_at timestamptz
)

study_session_concepts (                   -- N:M
  session_id uuid references study_sessions on delete cascade,
  concept_id uuid references concepts on delete cascade,
  primary key (session_id, concept_id)
)

push_subscriptions (
  id uuid pk, user_id uuid,
  endpoint text unique not null, p256dh text not null, auth text not null,
  user_agent text, active boolean default true,
  created_at timestamptz
)

api_tokens (                               -- para el atajo de Siri
  id uuid pk, user_id uuid,
  name text, token_hash text unique not null,   -- SHA-256; el token en claro solo se muestra una vez
  last_used_at timestamptz, revoked_at timestamptz,
  created_at timestamptz
)
```

Índices clave: `processing_jobs (status, next_run_at)`, `study_sessions (status, scheduled_at)`, `concepts (user_id, created_at desc)` y un índice de texto (`pg_trgm`) sobre `concepts.title` para la búsqueda.

---

## 3. Flujo de procesamiento

### 3.1 Captura → ficha

```
POST /concepts
  └─ inserta concept + job(generate_content, pending)  → responde 201 al instante

pg_cron (cada 1 min) → POST /internal/tick
  1. Toma hasta TICK_MAX_JOBS jobs con status=pending y next_run_at<=now()
     (UPDATE ... SET status='processing', locked_at=now() ... FOR UPDATE SKIP LOCKED)
  2. generate_content:
       stage=generating → Gemini → validar → insertar concept_content (version+1)
       → completed y crea job fetch_videos
  3. fetch_videos:
       stage=searching_videos → YouTube → insertar concept_resources → completed
  4. Si falla: attempts+1, last_error, next_run_at = now() + 2^attempts min
       si attempts >= max_attempts → failed
  5. Libera jobs atascados (processing con locked_at > 5 min) → pending
  6. Envía push de study_sessions con scheduled_at<=now() y status=scheduled
```

`POST /concepts/{id}/regenerate` crea un nuevo job `generate_content` y la ficha anterior se conserva como versión previa.

### 3.2 Panel de carga (requisito obligatorio)

El frontend no espera "a ciegas": consulta `GET /concepts/{id}/status` cada 3 s mientras haya un job activo y deja de consultar al terminar.

| Estado del job | `stage` | Texto en pantalla |
|---|---|---|
| `pending` | `queued` | «En cola, ya casi le toca…» |
| `processing` | `generating` | «Armando la explicación…» |
| `processing` | `searching_videos` | «Buscando videos en español…» |
| `completed` | `done` | «¡Listo!» → aparece la ficha con una transición |
| `failed` | — | «No se pudo generar» + motivo corto + botón **Reintentar** |

- Skeleton animado con la forma de la ficha y una barra de etapas; los textos rotan para que se sienta vivo.
- El concepto aparece en la biblioteca desde el primer segundo con una insignia de estado.
- Se puede seguir navegando y creando conceptos mientras tanto.
- Las animaciones respetan `prefers-reduced-motion`.

> Mejora opcional futura: intentar la generación justo al crear el concepto y dejar el tick como respaldo, para reducir la espera.

---

## 4. Esquema JSON de la ficha (`concept_content.content`)

```json
{
  "summary": "Una frase que lo explique a cualquiera.",
  "levels": {
    "basic": "Explicación sin jerga, con una analogía.",
    "intermediate": "Cómo funciona por dentro.",
    "technical": "Detalle técnico preciso."
  },
  "uses": ["Para qué sirve 1", "Para qué sirve 2"],
  "real_example": {
    "title": "Pipeline de una app web",
    "description": "Paso a paso de un caso real.",
    "code": "opcional: snippet",
    "code_language": "yaml"
  },
  "related_concepts": [
    { "name": "Docker", "why": "Se usa para empaquetar lo que despliega el pipeline." }
  ],
  "review_questions": [
    { "question": "¿Qué diferencia hay entre CI y CD?", "answer": "…" }
  ],
  "suggested_category": "DevOps",
  "suggested_tags": ["automatización", "despliegue"]
}
```

Reglas: todo en español; 3–6 `uses`, 2–6 `related_concepts`, 3–5 `review_questions`; `code` y `code_language` son opcionales. **El modelo no devuelve URLs**; los videos vienen solo de YouTube (`concept_resources`).

---

## 5. Contrato de API

Base: `/api/v1`. Autenticación con `Authorization: Bearer <JWT de Supabase>`, salvo donde se indica. Errores con formato `{ "error": { "code": "...", "message": "..." } }`.

### Conceptos

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/concepts` | Crear `{ title, original_text?, category_id?, tags? }` → 201 + concepto con `job_status` |
| `GET` | `/concepts` | Listar. Query: `q`, `category_id`, `status`, `tag`, `sort=created_at\|title`, `order`, `limit`, `cursor` |
| `GET` | `/concepts/{id}` | Concepto + ficha más reciente + videos + estado del job |
| `PATCH` | `/concepts/{id}` | Editar título, categoría, etiquetas o `learning_status` |
| `DELETE` | `/concepts/{id}` | Eliminar (en cascada) |
| `GET` | `/concepts/{id}/status` | Ligero para el polling: `{ status, stage, attempts, last_error }` |
| `POST` | `/concepts/{id}/regenerate` | Nueva versión de la ficha → 202 |
| `POST` | `/concepts/{id}/retry` | Reintentar un job `failed` → 202 |

### Categorías

`GET /categories`, `POST /categories`, `PATCH /categories/{id}`, `DELETE /categories/{id}`.

### Sesiones de estudio

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/sessions` | `{ title?, scheduled_at, timezone, concept_ids[] }` |
| `GET` | `/sessions` | Query `status`, `from`, `to` (próximas e historial) |
| `GET` | `/sessions/{id}` | Sesión + conceptos con sus fichas |
| `PATCH` | `/sessions/{id}` | Cambiar hora, conceptos o estado (`cancelled`, `done`) |
| `DELETE` | `/sessions/{id}` | Eliminar |

### Notificaciones

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/push/vapid-public-key` | Clave pública (sin auth) |
| `POST` | `/push/subscriptions` | Registrar `{ endpoint, keys: { p256dh, auth } }` |
| `DELETE` | `/push/subscriptions` | Darse de baja `{ endpoint }` |
| `POST` | `/push/test` | Enviar una notificación de prueba |

### Siri y tokens

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/tokens` | Crear token → lo devuelve **una sola vez** |
| `GET` | `/tokens` | Listar (sin el valor) |
| `DELETE` | `/tokens/{id}` | Revocar |
| `POST` | `/siri/concepts` | Auth `Bearer <token personal>`. Body `{ text }` → 201 `{ message: "Guardado: CI/CD" }` |

### Interno

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/internal/tick` | Solo con `X-Tick-Secret`. Procesa jobs y envía push |
| `GET` | `/health` | Estado del servicio (sin auth) |

### Cómo se aplican los permisos

- Peticiones del usuario: el backend valida el JWT y consulta Supabase **con ese mismo JWT**, así RLS filtra los datos.
- Tick y Siri: usan la clave `service_role` (solo en el backend) y filtran siempre por `user_id` de forma explícita.

---

## 6. Variables de entorno

`backend/.env.example`

```
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_JWT_ISSUER=
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.8-flash
GEMINI_FALLBACK_MODEL=gemini-3.5-flash-lite
YOUTUBE_API_KEY=
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
VAPID_SUBJECT=mailto:tu-correo@ejemplo.com
TICK_SECRET=
TICK_MAX_JOBS=3
CORS_ORIGINS=http://localhost:5173
```

`frontend/.env.example` (solo valores públicos)

```
VITE_API_URL=http://localhost:8000/api/v1
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
VITE_VAPID_PUBLIC_KEY=
```

El `TICK_SECRET` también se guarda en Supabase (Vault) para que `pg_cron` lo envíe.

---

## 7. Criterios de aceptación

**Fundamentos**
- [ ] Registro e inicio de sesión funcionan en la PWA desplegada.
- [ ] Un usuario no puede leer datos de otro (probado con dos cuentas).
- [ ] `/health` responde en Vercel.

**Biblioteca**
- [ ] Crear, editar y eliminar conceptos; los cambios se ven sin recargar.
- [ ] Búsqueda por título, filtros por categoría/estado/etiqueta y orden por fecha o nombre.

**IA y panel de carga**
- [ ] El concepto se guarda aunque Gemini esté caído.
- [ ] Mientras se genera, se ve el panel de carga con sus etapas y la app no se congela.
- [ ] La ficha aparece sola al terminar, en menos de ~2 minutos en condiciones normales.
- [ ] Un fallo muestra el motivo y el botón Reintentar; un 429 se reintenta con espera.
- [ ] Los videos son enlaces reales de YouTube y en español cuando existen.

**Estudio y notificaciones**
- [ ] Programar una sesión con conceptos y recibir la notificación en el iPhone (PWA instalada) con un margen de ±2 minutos.
- [ ] Tocar la notificación abre la sesión correcta.
- [ ] Cancelar una sesión evita la notificación.

**Siri**
- [ ] Dictar un concepto desde el atajo lo crea y Siri confirma «Guardado».
- [ ] Un token revocado devuelve 401.

---

## 8. Pendientes

- [ ] Anotar los límites reales de Gemini al crear la clave en AI Studio.
- [ ] Confirmar el tiempo máximo de función en Vercel Hobby al hacer el primer despliegue y ajustar `TICK_MAX_JOBS`.
- [ ] Probar pronto en el iPhone que la PWA instalada recibe push.
