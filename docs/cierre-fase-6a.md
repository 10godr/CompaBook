# Cierre de la Fase 6a: Cuaderno y ficha con Gemini

Cerrada el 2026-10-24. Entregada en los PR #25 a #29. Verificada en local con **Gemini real** y un recorrido en Chrome (33 comprobaciones), y **en producción** por Emile el mismo día (ver «Verificación en producción»).

## Qué entrega

- **Crear un concepto.** El usuario escribe un título (1–200 caracteres); se guarda **antes** de llamar a la IA, junto con su trabajo en cola. Si Gemini falla, el concepto no se pierde.
- **Ficha al momento.** Al abrir el concepto, la web pide la generación (`POST /concepts/{id}/process`). Gemini devuelve una ficha estructurada en el idioma del usuario (**Qué es**, **Para qué sirve**, **Ejemplo** y, a veces, un bloque de código), que se valida antes de guardarse.
- **Fichas compartidas.** La ficha se guarda una sola vez por `(cache_slug, idioma)` y no lleva datos de nadie; dos usuarios con el mismo `cache_slug` terminan con la misma.
- **Panel de carga** con barra de etapas (En cola → Escribiendo → ¡Listo!), texto de la etapa y esqueleto; se actualiza cada 2 s. Pasados 3 minutos sin terminar avisa de que tarda más de lo normal.
- **Reintentar** manual cuando falla: deja el **mismo** trabajo en cola y vuelve a generar. Si la ficha ya estaba guardada, no llama a Gemini.
- **Cuaderno:** lista del más nuevo al más viejo, búsqueda (`ILIKE` por usuario), «Cargar más», estado en cada tarjeta, eliminar con confirmación. **Inicio:** campo para añadir, uso del día y últimos conceptos.
- **Límites diarios** por usuario y por **día local** (`users.timezone`): 30 conceptos y 10 reintentos. Eliminar un concepto no devuelve el cupo.
- **Aislamiento:** todo pasa por repositorios con el `user_id` de la sesión; un concepto ajeno responde 404, igual que uno inexistente.
- **Seguridad del contenido:** el texto de la IA y los títulos se pintan siempre como texto, nunca como HTML. El concepto va a Gemini delimitado como dato y sin poder cerrar la etiqueta. Ni el concepto, ni la clave, ni la respuesta aparecen en los logs; solo modelo, resultado, código y milisegundos.

### Cómo funciona `/process`

1. Reclama el trabajo con `FOR UPDATE SKIP LOCKED` y **confirma**.
2. Llama a Gemini **sin ninguna transacción abierta**.
3. Guarda la ficha (`ON CONFLICT (cache_slug, language) DO NOTHING`) y completa el trabajo en otra transacción.

Si otro proceso ya lo tiene, responde 202. Si Gemini falla, el trabajo pasa **directamente a `failed`** (en la 6a no hay quien lo reintente solo) y se guarda solo el tipo de error. Un trabajo `processing` de hace más de 5 minutos (la función murió a medias) se informa como `failed` y Reintentar lo acepta.

### Gemini: lo que se comprobó con la API real (2026-10-24)

| Modelo | Resultado | Cupo gratuito (AI Studio) |
|---|---|---|
| `gemini-3.8-flash`, `3.7-flash` | Sin respuesta en 60 s o 503 «high demand» | 5 RPM / 20 RPD (`3.8`, `3.6`) |
| `gemini-3.6-flash` | 503 | 5 RPM / 20 RPD |
| **`gemini-3.5-flash`** (principal) | 200, unos 10 s | no figuraba aún |
| **`gemini-3.5-flash-lite`** (respaldo) | 200, 5–10 s | 15 RPM / 500 RPD |
| `gemini-3.1-flash-lite` | 200, 18 s | 15 RPM / 500 RPD |
| `gemini-2.5-flash` | 404: ya no está para cuentas nuevas | |

- Por eso el principal pasó de `gemini-3.8-flash` a **`gemini-3.5-flash`**. Cambiarlo es solo la variable `GEMINI_MODEL`.
- **Los 503 son frecuentes** en el plan gratuito: en el recorrido, el principal falló casi siempre y atendió el respaldo. El usuario lo ve como «No se pudo generar» y pulsa Reintentar.
- **Con el respaldo, las claves de ficha son menos estables:** «integración continua» dio `integracion-continua` y `integration-continua`. Con `gemini-3.5-flash`, «CI/CD» y «integración continua» dieron el mismo `ci-cd`. Es un ajuste de prompt para la 6b.
- Con 30 conceptos por usuario y día y pocos usuarios invitados, los 500 RPD del respaldo cubren el uso; el límite de 30 no se cambia.

## Archivos

### Backend (`backend/`)
- `app/services/ai.py`: `AIProvider`, `GeminiProvider` (REST con `httpx`, respaldo, errores solo con su tipo), `CardContent` (validación) y `normalize_slug`.
- `app/services/concepts.py`: crear, procesar, reintentar, límites del día local, estado.
- `app/api/concepts.py` (`/concepts`) y `app/api/me.py` (`usage` en `GET /me`).
- `app/repositories/concepts.py`: `ConceptRepository` (con `user_id`, incluye reclamar/fallar/completar/reiniciar el trabajo) y `ConceptCardRepository`.
- `app/models/concepts.py` y la migración `0003_conceptos`.
- `app/config.py` (variables nuevas, abajo) y `vercel.json` (`maxDuration: 60` para `api/index.py`).
- `tests/`: `test_ai`, `test_conceptos_api`, `test_conceptos_repos`, `test_conceptos_schema`; `helpers.py` (`FakeAIProvider`, `make_content`) y `conftest.py` (fixture `ai`).

### Frontend (`frontend/src/`)
- `concepts/`: `types.ts`, `useConceptList.ts`, `useConcept.ts`, `useUsage.ts`, `format.ts`; `useDebounced.ts`.
- `pages/`: `Home`, `Notebook`, `Concept` (ruta `/cuaderno/:id`).
- `components/`: `AddConcept`, `ConceptRow`, `ConceptMenu`, `StatusPill`, `Toast`, `LoadingPanel`, `CardView`.
- `i18n/es.json` y `en.json` (claves `home.*`, `notebook.*`, `concept.*`, `status.*`) y estilos en `index.css`.
- `test/concepts.ts` y `mockApi.ts` (ahora admite respuestas asíncronas).

### Documentación
- `diseno-tecnico.md`: §1.2 (Gemini por REST, modelos y por qué), §4.1 (cómo se comporta la 6a sin reloj), §5.2 (validación), §7 (contrato de `/concepts` y `/me`), §8.2 (variables).
- `contexto.md` (§5.5 día local, §11), `design.md` (barra de etapas de 3 pasos en la 6a).

## Pruebas

- **Backend:** 342 pruebas con pytest sobre PostgreSQL real (51 nuevas en el API y repositorios, 76 en la capa de IA con transporte simulado); `ruff check` y `ruff format --check` limpios. Cubren, entre otras cosas: el concepto se guarda aunque la IA falle, la IA no se llama con la transacción abierta, un proceso concurrente recibe 202 sin llamar a la IA, trabajo abandonado, reintentos y su límite, el concepto 31 da 429 sin crearse, el día local con cruce de medianoche UTC, paginación sin perder ni repetir, 404 en cada endpoint con dos usuarios, borrar la cuenta borra conceptos y deja las fichas, y que los logs no contienen el concepto.
- **Frontend:** 123 pruebas con Vitest (44 nuevas); `tsc`, `oxlint` y `npm run build` limpios. Incluye una que obliga a que `es.json` y `en.json` tengan las mismas claves y parámetros.
- **Mutaciones:** se comprobó que las pruebas fallan si se quita el filtro de usuario, si el día pasa a ser UTC, si se llama a la IA con la transacción abierta, si el título llega al log, si la ficha o el título se pintan como HTML, si desaparece la espera del buscador y si una respuesta tardía pisa a la actual.
- **Navegador real con Gemini real:** 33 comprobaciones con Chrome automatizado (móvil oscuro, escritorio oscuro y claro) contra el backend local y la base de Docker; no están en el repo. Cubren el registro, añadir, panel de carga, ficha con código y Copiar, contador, Cuaderno, búsqueda, eliminar, Reintentar sobre un fallo, límite diario y concepto inexistente, sin errores en la consola.
- **Producción (sin sesión):** `/api/v1/health` da 200; `GET` y `POST /api/v1/concepts` sin sesión dan 401.

## Configuración necesaria

Variables del backend (Vercel en Production y Preview, y `backend/.env` en local; nunca en el repo ni en el chat). Ver `backend/.env.example`.

| Variable | Para qué | Por defecto |
|---|---|---|
| `GEMINI_API_KEY` | Clave de Google AI Studio | Sin ella, generar da `not_configured` |
| `GEMINI_MODEL` | Modelo principal | `gemini-3.5-flash` |
| `GEMINI_FALLBACK_MODEL` | Respaldo ante 429, caída o respuesta inservible | `gemini-3.5-flash-lite` |
| `AI_TIMEOUT_SECONDS` | Espera por llamada a Gemini | `25` (el peor caso con respaldo es el doble) |
| `DAILY_CONCEPT_LIMIT` / `DAILY_RETRY_LIMIT` | Límites por usuario y día local | `30` / `10` |
| `CONCEPT_TITLE_MAX` | Largo máximo del título | `200` (no puede pasar de 200: lo impide la base) |

Base de datos: la migración `0003_conceptos` se aplicó a `compabook-prod` a mano (SQL de Alembic en el editor de Supabase). En local, `alembic upgrade head`.

## Verificación en producción

Emile la probó el 2026-10-24 con una cuenta invitada en `https://compabook.vercel.app`: todo funcionó sin ningún error, el contador de Inicio subió y en los registros de Vercel aparecieron las líneas de Gemini. Los pasos probados fueron:

1. Añadir un concepto desde Inicio: aparece el panel de carga, pasa de «En cola» a «Escribiendo» enseguida y termina en la ficha. Anotar cuánto tarda.
2. Si da «No se pudo generar», pulsar Reintentar (los 503 son normales hoy).
3. Que el contador de Inicio suba y que la ficha aparezca en el Cuaderno; buscarla y eliminarla.
4. Comprobar que una generación que pase de 10 s no se corta (confirma `maxDuration: 60`). No se reportaron cortes; si Vercel cortara alguna, plan B: `/process` responde 202 y la termina el reloj de la 6b.
5. En los registros de Vercel solo deben verse líneas `gemini model=… outcome=… ms=…`, sin el concepto.

## Criterios de aceptación de la 6a (`diseno-tecnico.md` §11)

| Criterio | Estado |
|---|---|
| El concepto se guarda aunque Gemini esté caído | ✅ Pruebas y recorrido real |
| Ficha en el idioma del usuario, venga el concepto en el que venga | ✅ Pruebas (el idioma de la ficha es el de la cuenta) |
| «En cola» dura menos de 5 s | ✅ En local pasa a «Escribiendo» al instante; en producción no se notó demora (no se cronometró) |
| Panel de carga por etapas, sin congelar la app | ✅ |
| Un fallo muestra **Reintentar** y funciona; si la ficha existía, no se llama a Gemini | ✅ Pruebas y recorrido real |
| Límite diario con mensaje claro y sin crear el concepto | ✅ |
| Búsqueda y eliminación en el Cuaderno | ✅ |
| Aislamiento entre usuarios en `/concepts` | ✅ |
| Eliminar la cuenta borra los conceptos | ✅ |
| Dos usuarios con la misma ficha terminan con una sola | ✅ Con el mismo `cache_slug` (`ON CONFLICT`); la reutilización por alias es de la 6b |
| Si se cierra la pestaña a mitad, la ficha se completa | ➡ 6b (reloj). En la 6a, al volver a abrir el concepto se reanuda |
| 2 videos, reutilización de videos, ficha sin llamar a Gemini por alias, título de más de 60 caracteres sin alias | ➡ 6b |

## Pendientes

- **6b:** reloj `/internal/jobs` con reintentos automáticos (hoy un 503 deja el trabajo en `failed`), videos con caché, alias y reutilización de fichas, y **estabilizar el `cache_slug`** en el prompt (los slugs del modelo de respaldo cambian entre ejecuciones).
- **Gemini:** anotar el cupo de `gemini-3.5-flash` cuando aparezca en AI Studio y volver a probar `gemini-3.8-flash` en unos días.
- **`GET /me` se lee dos veces** al abrir Inicio (sesión y uso del día). Se puede unificar en `AuthProvider`.
- **Migraciones fuera de local:** se siguen aplicando a mano; se reconsidera en la 6b.
- **Cierre de la Fase 4** (a partir del 2026-10-30): prueba H de la cookie, revisar y parar el `pg_cron` de prueba (`compabook-ping`, **no** `compabook-cleanup`), retirar el código temporal y los enlaces `Prueba de cookie` / `Prueba de push` de Inicio.
- **Limpieza diaria:** confirmar en `cron.job_run_details` que `compabook-cleanup` corrió sola.
- Pendientes de Supabase en `contexto.md` §12 (pausa por inactividad, copias de seguridad).
