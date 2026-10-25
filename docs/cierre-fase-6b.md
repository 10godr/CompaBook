# Cierre de la Fase 6b: cola, videos y fichas compartidas

Cerrada en código el 2026-10-25. Entregada en los PR #30 a #34. Verificada en local con **Gemini y YouTube reales** (un recorrido en Chrome de 45 comprobaciones y una prueba de la capa de trabajos). La verificación en producción está **parcial**: ver «Verificación en producción».

## Qué entrega

- **Videos.** Cada ficha lleva 2 videos de YouTube (miniatura, título y canal). Se buscan con la consulta `youtube_search_query` que escribe Gemini junto con la ficha y se guardan en `video_cache` por `(cache_slug, idioma)`: dos usuarios que llegan a la misma ficha comparten los videos y YouTube se consulta una sola vez. El clic abre YouTube en otra pestaña.
- **Alias.** Si ese mismo texto (normalizado: minúsculas, sin tildes y con los espacios colapsados; los signos como `/` se conservan) ya se vio en ese idioma, el concepto recibe la ficha existente **sin llamar a Gemini**. El alias se guarda después de guardar la ficha, para que nunca apunte a algo que no existe. Un título de más de 60 caracteres normalizados no crea alias. Crear el concepto cuenta para el límite diario aunque acierte el alias.
- **Fichas compartidas más estables.** El prompt pide un `cache_slug` más estable (sustantivo canónico, singular, sin versiones ni marcas). Medido con `gemini-3.5-flash-lite` en 24 conceptos: el acuerdo entre formas de escribir lo mismo pasó de 15/24 a 18/24. Los casos vecinos (CI vs CI/CD, containers vs Docker, version-control vs Git) siguen dando fichas distintas: cuesta una ficha duplicada, no un error.
- **Trabajador compartido** (`services/jobs.py`). `POST /concepts/{id}/process` (el usuario, al momento) y `POST /internal/jobs` (el reloj) ejecutan **el mismo código**. Se reclama el trabajo con `FOR UPDATE SKIP LOCKED` y se confirma; Gemini y YouTube se llaman **sin ninguna transacción abierta**; el resultado se guarda en otra.
- **Reintentos automáticos.** Un fallo pasajero (`busy`, `unavailable`, `invalid_response`, fallo nuestro) deja el trabajo en cola con espera de **2 y luego 4 minutos**; al tercer intento en total pasa a `failed`. `/process` respeta la espera (responde 202 sin llamar a nadie). `rejected` y `not_configured` **no** se reintentan solos: volver a preguntar no ayuda y gastaría cuota; pasan directo a `failed` y la persona decide pulsar **Reintentar**.
- **Trabajos abandonados.** Un `processing` con más de 5 minutos (la función murió a medias) se ve como `pending`/`queued` y lo recoge el siguiente `/process` o el reloj. Ese intento abandonado **cuenta**; si con él se llega al máximo, pasa a `failed` (`abandoned`). Por eso `retry` ahora solo acepta trabajos `failed`.
- **Reloj** `POST /internal/jobs`: toma hasta `JOBS_MAX_PER_RUN` (3) trabajos a los que ya les toca, de todos los usuarios, **de uno en uno**, y no empieza otro pasados `JOBS_BUDGET_SECONDS` (30 s). Un trabajo roto no para a los demás. Responde solo contadores `{due, completed, retrying, failed, skipped}`.
- **Si YouTube falla** (cuota, caída, respuesta inválida) la ficha se completa **sin videos**: no se marca `failed`, el fallo **no** se guarda en `video_cache` y no se reintenta por su cuenta; el siguiente concepto con esa ficha vuelve a buscar. La pantalla dice «No encontramos videos para este concepto».
- **Interfaz.** Sección «Videos» debajo de la ficha (dos en fila en escritorio, apiladas en móvil), barra de **4 pasos** (En cola → Escribiendo → Buscando videos → ¡Listo!) y el texto «Reintentando…» cuando el trabajo volvió a la cola tras un fallo.

### Decisiones de la 6b (aprobadas con el plan)

1. Los videos se leen por `(cache_slug, idioma)` al pedir el concepto, no se copian a cada concepto.
2. Un fallo de YouTube no hace fallar la ficha ni se cachea.
3. `/process` y el reloj comparten código; `/process` respeta `next_run_at`; un `processing` abandonado se muestra como en cola y cuenta como intento.
4. Reloj: máx. 3 trabajos por llamada y presupuesto de 30 s; 3 intentos en total con esperas de 2 y 4 min; `pg_net` con `timeout_milliseconds := 58000`.
5. `youtube_search_query` se guarda en `concept_cards`; las fichas de la 6a usan su `canonical_title`.
6. La estabilidad del `cache_slug` se consigue solo con el prompt (sin fusionar fichas a posteriori).
7. El reloj no tiene sesión: `JobQueueRepository.due()` lista trabajos de **todos** los usuarios y devuelve solo ids (**excepción documentada** a la regla del `user_id`); el trabajo se hace luego con los repositorios de siempre y el `user_id` del trabajo.
8. Lo que llega de YouTube es dato no confiable: se decodifican las entidades HTML del título, el `youtube_id` debe ser de 11 caracteres `[A-Za-z0-9_-]` y solo se aceptan miniaturas `https` de `ytimg.com`; en pantalla se pinta como texto.

### Lo que se comprobó con la API real

- **YouTube Data API:** cuota de **10 000 unidades al día**; `search.list` cuesta **100**, es decir, unas **100 búsquedas al día** para todos los usuarios. La caché de videos por ficha y los alias son lo que lo hace alcanzar. Se piden 5 resultados y se guardan los 2 primeros válidos (`videoEmbeddable=true`, `safeSearch=moderate`, `relevanceLanguage` del idioma).
- **Fuga evitada:** `httpx` registra la URL completa de cada petición a nivel INFO, y la URL de YouTube lleva la consulta. Se silencia el logger `httpx` en `services/youtube.py` y hay una prueba que lo exige. La clave va en la cabecera `x-goog-api-key`, nunca en la URL.
- **Gemini sigue dando 429 y 503** en el modelo principal; atiende el de respaldo. En la prueba real, el principal dio un 503 y un 429 y respondió `gemini-3.5-flash-lite`. Pedirle a Gemini consultas con tildes no funcionó (las quita igual) y se revirtió: YouTube busca bien sin ellas.

## Archivos

### Backend (`backend/`)
- `app/services/jobs.py` (nuevo): `process_concept`, `run_job`, `run_due_jobs`, reintentos y esperas.
- `app/services/youtube.py` (nuevo): `VideoProvider`, `YouTubeProvider`, validación de datos no confiables, logger de `httpx` silenciado.
- `app/services/aliases.py` (nuevo): `normalize_title`.
- `app/services/ai.py`: el prompt pide `youtube_search_query` y un `cache_slug` más estable.
- `app/services/concepts.py`: sin `process_concept`; `job_state` muestra el abandonado como en cola.
- `app/api/concepts.py` (videos en el detalle, `/process` con el trabajador compartido) y `app/api/internal.py` (`POST /internal/jobs`).
- `app/repositories/concepts.py`: `claim_job`, `set_stage`, `fail_job` con reintento, `JobQueueRepository.due`, `ConceptAliasRepository`, `VideoCacheRepository`.
- `app/models/concepts.py` y la migración **`0004_alias_videos`** (`concept_cards.youtube_search_query`, tablas `concept_aliases` y `video_cache`, ambas con RLS).
- `app/config.py` y `.env.example` (variables nuevas, abajo).
- `tests/`: `test_trabajos`, `test_youtube`, `test_alias_normalizacion`, `test_alias_videos_schema`; ampliados `test_ai`, `test_conceptos_api` y `test_conceptos_repos`; `helpers.py` (`FakeVideoProvider`) y `conftest.py` (fixture `youtube`).

### Frontend (`frontend/src/`)
- `components/VideoCards.tsx` (nuevo), `CardView.tsx` (sección de videos), `LoadingPanel.tsx` (4 pasos y «Reintentando…»).
- `concepts/types.ts` (tipo `Video`), `pages/Concept.tsx`, `i18n/es.json` y `en.json`, `index.css`.
- `test/concepts.ts` y `pages/Concept.test.tsx`.

### Documentación
- `diseno-tecnico.md`: §4.1 (semántica del trabajador compartido), §4.2 (SQL de `compabook-jobs` con `timeout_milliseconds`), §4.3 (reintentos, errores no reintentables, reglas de YouTube, contadores de log), §4.4 (reloj y la excepción del `user_id`), tabla de la API y variables.
- `design.md`: la barra de etapas tiene 4 pasos y «Reintentando…».
- `contexto.md` §11 (6b).

## Pruebas

- **Backend:** **527** pruebas con pytest sobre PostgreSQL real (185 más que al cerrar la 6a); `ruff check` y `ruff format --check` limpios. Cubren, entre otras cosas: normalización de alias, el esquema de `concept_aliases` y `video_cache` (claves, `CHECK`, RLS, borrado en cascada), validación de lo que manda YouTube, que no se llama a la IA con alias, que los videos se cachean y se comparten entre usuarios, que un fallo de YouTube deja la ficha completa sin cachear nada, reintentos con espera de 2 y 4 min y el límite de 3 intentos, errores no reintentables, abandonados (cuentan como intento), `/process` respetando `next_run_at`, el reloj (máximo por llamada, presupuesto de tiempo, un trabajo roto no para a los demás, solo contadores), que el endpoint exige el secreto y que los logs no contienen títulos, consultas ni claves.
- **Frontend:** **132** pruebas con Vitest (9 nuevas); `tsc`, `oxlint` y `npm run build` limpios.
- **Mutaciones:** se comprobó que las pruebas fallan si todo se reintenta, si se desactivan los alias, si la espera es de 3 min, si no hay caché de videos, si se ignora el presupuesto de tiempo, si el abandonado no cuenta, si se ignora `next_run_at`; y en la interfaz: quitar el paso de videos, quitar «Reintentando…», pintar el título como HTML, quitar `noopener`, quitar `lazy`, enlazar a otra URL, mostrar siempre el canal y quitar el aviso de «sin videos». *Una mutación sobrevivió a propósito:* hacer que un error de YouTube se propague no rompe nada, porque `run_job` lo atrapa por segunda vez (comportamiento equivalente).
- **Prueba real de la capa de trabajos** (Gemini y YouTube reales, base local, limpiada después): «recursividad» y «Recursión » llegaron a la misma ficha `recursion` con **una sola** búsqueda en YouTube (la segunda salió de la caché) y 2 alias.
- **Navegador real, Gemini y YouTube reales:** 45 comprobaciones con Chrome automatizado contra el backend local y la base de Docker (no están en el repo; la base quedó vacía al terminar). Cubren: ficha con 2 videos reales y miniaturas descargadas, enlaces a `youtube.com/watch` con `noopener`, títulos sin entidades HTML, disposición apilada/en fila, miniatura 16:9, título a 2 líneas, brillo al pasar el ratón; el segundo texto con la misma ficha y videos de la caché (`alias=miss videos=hit`) y el mismo texto normalizado con `alias=hit videos=hit` y **cero** llamadas a Gemini; la etapa «Buscando videos» y el paso a la ficha; un trabajo que espera su reintento muestra «Reintentando…», abrir la pantalla no llama a Gemini, `POST /internal/jobs` lo procesa y la pantalla termina sola; secreto equivocado → 401; sin videos → aviso; y que ni los títulos, ni la consulta de YouTube, ni la clave aparecen en los registros del backend.

## Configuración necesaria

Variables del backend (Vercel en Production y Preview, y `backend/.env` en local; nunca en el repo ni en el chat). Ver `backend/.env.example`.

| Variable | Para qué | Por defecto |
|---|---|---|
| `YOUTUBE_API_KEY` | Clave de la YouTube Data API (restringida a esa API) | Sin ella, no hay videos (la ficha sale igual) |
| `YOUTUBE_TIMEOUT_SECONDS` | Espera por búsqueda en YouTube | `10` |
| `JOBS_MAX_PER_RUN` | Trabajos máximos por llamada del reloj | `3` |
| `JOBS_BUDGET_SECONDS` | Tras estos segundos el reloj no empieza otro trabajo | `30` |

**Base de datos:** la migración `0004_alias_videos` se aplicó a `compabook-prod` a mano (SQL de Alembic en el editor de Supabase; el archivo `.py` de la migración **no** se pega ahí) y Emile confirmó que quedó bien. En local, `alembic upgrade head`.

**Reloj en Supabase** (`pg_cron` + `pg_net`), tarea `compabook-jobs` cada minuto contra `https://compabook.vercel.app/api/v1/internal/jobs` con el secreto leído de Vault (`internal_secret`). El SQL está en `diseno-tecnico.md` §4.2. Lleva `timeout_milliseconds := 58000`: `pg_net` espera solo 5 s por defecto y un trabajo puede tardar hasta unos 60 s (modelo principal 25 s + respaldo 25 s + YouTube 10 s). Para pararla: `select cron.unschedule('compabook-jobs');`. Emile la creó el 2026-10-25.

## Verificación en producción

Hecho:
- Migración `0004` aplicada en `compabook-prod` (confirmado por Emile).
- Tarea `compabook-jobs` creada en Supabase (confirmado por Emile).

**Pendiente de anotar** (todavía no se ha reportado el resultado):
1. `select status, return_message, start_time from cron.job_run_details where jobid = (select jobid from cron.job where jobname = 'compabook-jobs') order by start_time desc limit 5;` → `succeeded`.
2. `select status_code, timed_out, content, created from net._http_response order by created desc limit 5;` → `status_code = 200`, `timed_out = false` y `content` con los cinco contadores.
3. Crear un concepto nuevo en `https://compabook.vercel.app`: debe pasar por «En cola» → «Escribiendo» → «Buscando videos» y terminar con **2 videos** cuyo clic abra YouTube.
4. Escribir el mismo concepto de otra forma y comprobar que sale más rápido y con los mismos videos.
5. **Un trabajo largo de verdad** (cuando Gemini dé 503 en el principal y conteste el respaldo): comprobar que `net._http_response` sigue en 200 y no en timeout. Puede tardar en darse; no hay que forzarlo.
6. En los registros de Vercel solo deben verse líneas `gemini model=… outcome=…`, `trabajo terminado alias=… videos=…` y `jobs: {…}`, sin ningún concepto.

## Criterios de aceptación de la 6b (`diseno-tecnico.md` §11)

| Criterio | Estado |
|---|---|
| Se muestran 2 videos con miniatura y título; el clic abre YouTube | ✅ Pruebas y recorrido real en local; falta verlo en producción |
| Un segundo usuario que pide el mismo concepto (aunque lo escriba distinto) reutiliza los videos | ✅ Pruebas con dos usuarios y recorrido real (`miss/hit`) |
| Un segundo usuario que escribe el mismo texto (normalizado) recibe la ficha sin llamar a Gemini | ✅ Prueba con `FakeAIProvider` que cuenta llamadas y recorrido real (cero llamadas) |
| Dos usuarios que piden a la vez un concepto nuevo terminan con una sola ficha | ✅ `ON CONFLICT DO NOTHING` sobre `(cache_slug, language)` y alias con `add_if_absent`, con prueba |
| Un título de más de 60 caracteres normalizados no crea alias | ✅ |
| Si se cierra la pestaña a mitad, la ficha se completa gracias al reloj | ✅ En pruebas y local (`POST /internal/jobs`); falta verlo con `pg_cron` en producción |
| Un fallo muestra **Reintentar** y funciona; si la ficha ya existía, no se llama a Gemini | ✅ (los fallos pasajeros ahora se reintentan solos antes de llegar ahí) |
| Prueba de concepto: `pg_cron` llama a `/internal/jobs` en producción y queda en los logs | ➡ Pendiente de anotar el resultado (ver arriba) |

## Pendientes

- **Verificación en producción** de la sección anterior, en especial `status_code = 200` con un trabajo largo.
- **Cuotas:** YouTube da unas 100 búsquedas al día para todos; vigilar el uso cuando haya más usuarios. Anotar el cupo de `gemini-3.5-flash` cuando aparezca en AI Studio y volver a probar `gemini-3.8-flash` en unos días.
- **Fichas duplicadas entre conceptos vecinos** (CI vs CI/CD, containers vs Docker): es un coste, no un error. Si molesta, se puede fusionar a posteriori; no se hizo (decisión 6).
- **Migraciones fuera de local:** se siguen aplicando a mano en el editor de Supabase.
- **`GET /me` se lee dos veces** al abrir Inicio (sesión y uso del día). Se puede unificar en `AuthProvider`.
- **Cierre de la Fase 4** (a partir del 2026-10-30): prueba H de la cookie en la PWA instalada, revisar y parar el `pg_cron` de prueba (`compabook-ping`, **no** `compabook-cleanup` ni `compabook-jobs`), retirar el código temporal (`backend/app/poc*.py` y sus pruebas, `frontend/public/sw.js`, `PruebaCookie.tsx`, `PruebaPush.tsx`, rutas `/prueba-*`, enlaces en Inicio y Bienvenida, estilos `.poc`) y escribir su documento de cierre.
- **Limpieza diaria:** confirmar en `cron.job_run_details` que `compabook-cleanup` corrió sola.
- Pendientes de Supabase en `contexto.md` §12 (pausa por inactividad, copias de seguridad).
- **Siguiente:** Fase 7 (recordatorios con push, con pruebas en iPhone y Android).
