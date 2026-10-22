# CompaBook — Contexto del proyecto

> Referencia principal del proyecto para el equipo (Diego Rodriguez y Emile Rosario) y para Claude Code.
> **Estado:** diseño funcional y técnico aprobado por el equipo el 2026-10-22 (PR #1). Siguiente: Fase 4. Aún no se ha escrito código.
> Nombre del producto: **CompaBook**. La sección donde el usuario guarda sus conceptos se llama «Cuaderno» (*Notebook* en inglés).

### Prioridad entre documentos

Si dos documentos se contradicen, manda el de más arriba:

1. **`contexto.md`** (este): qué es CompaBook, decisiones y alcance.
2. [`diseno-tecnico.md`](diseno-tecnico.md): cómo se construye.
3. [`design.md`](design.md): cómo se ve.

Un cambio de decisión se hace primero aquí y después se propaga a los demás.

---

## 0. Forma de trabajo

1. **No se escribe código sin aprobación explícita.** Primero se analiza, se plantean dudas y se presenta un plan.
2. **Se trabaja por fases**, probando cada parte antes de continuar.
3. **Git:** una rama por tarea (`docs/...`, `feat/...`, `fix/...`) y se integra a `main` mediante Pull Request revisado por el otro miembro. Commits pequeños y en español.
4. **Integración continua:** cada PR ejecuta automáticamente lint, tests y build (GitHub Actions). No se integra un PR en rojo.
5. **Entornos separados:** nunca se desarrolla ni se prueba contra la base de datos de producción (ver §4.1).
6. **Al cerrar cada fase** se documenta: archivos modificados, pruebas realizadas, configuración necesaria y pendientes reales.
7. El equipo está aprendiendo: las decisiones relevantes se explican.

---

## 1. Visión del producto

Aplicación web **multiusuario** para entender conceptos rápido. No es un curso ni sigue lecciones: es una pasada breve para entender algo y guardarlo.

1. El usuario se **registra** (email + contraseña, verificado con código) y elige su **idioma: español o inglés**.
2. **Escribe o dicta (Siri)** un concepto, p. ej. «CI/CD». Puede escribirlo en cualquier idioma.
3. El concepto se **guarda inmediatamente**, aunque la IA falle o tarde.
4. Un agente de IA genera **en el momento**, en el idioma del usuario, una ficha breve:
   - **Qué es** (definición).
   - **Para qué sirve.**
   - **Un ejemplo.**
   - **2 videos de YouTube** en su idioma.
5. Mientras se genera, se ve un **panel de carga animado**; la app nunca se congela.
6. La ficha queda **guardada en su Cuaderno**. Ahí termina ese concepto: el usuario decide si ve los videos o vuelve a leerla.
7. El usuario elige **a qué hora y qué días** quiere un **recordatorio** para repasar su Cuaderno.

---

## 2. Decisiones tomadas

| Tema | Decisión |
|---|---|
| Usuarios | **Multiusuario** con cuentas propias; cada usuario solo ve sus datos |
| Plataforma | **PWA** instalable en iPhone y usable en computadora |
| Login | **Propio** (sin Supabase Auth): email + contraseña, verificación por código, recuperación de contraseña. Solo email por ahora |
| Sesión | **Cookie segura `httpOnly`** con token de sesión guardado (hasheado) en la base de datos; 30 días que se renuevan con el uso. Sin cookies de analítica ni publicidad |
| Base de datos | **PostgreSQL alojado en Supabase**, accedido con **SQLAlchemy** y migraciones con **Alembic** |
| Uso de Supabase | Solo como **base de datos** y **`pg_cron`** (reloj). No se usa su Auth ni su API automática |
| Entornos | **Local** (PostgreSQL en Docker), **pruebas** (proyecto Supabase aparte, usado por los previews de Vercel) y **producción** (proyecto Supabase propio) |
| Backend | **Python + FastAPI** |
| Frontend | **React + TypeScript + Vite** (PWA) |
| Hosting | **Vercel** (Hobby), subdominio `*.vercel.app`. Sin dominio propio por ahora. Frontend y backend en el **mismo proyecto y mismo dominio** (el backend en `/api`) para que la cookie de sesión funcione en Safari de iPhone |
| Procesamiento | La ficha se genera **al momento** (el frontend la dispara al crear el concepto); el reloj `pg_cron` es el **respaldo** para reintentos y trabajos colgados |
| Correos | **Gmail del proyecto** por SMTP con contraseña de aplicación, detrás de `EmailProvider` (migrable a Resend cuando haya dominio) |
| IA | **Gemini API, nivel gratuito**, detrás de `AIProvider` |
| Videos | **YouTube Data API**, 2 videos en el idioma del usuario, **reutilizando** resultados ya buscados con una clave estable que da la IA |
| Idiomas | Español e inglés, para la interfaz y para el contenido |
| Recordatorios | Notificaciones **Web Push**: una hora al día y días de la semana elegidos por el usuario |
| Voz | **Atajo de Siri** con token personal por usuario |
| Límites de uso | **Límite suave por usuario** para proteger las cuotas compartidas: 30 conceptos y 10 reintentos al día; título de máximo 200 caracteres. Configurables por variable de entorno |
| Calidad | **GitHub Actions** en cada PR: `ruff` + `pytest` (backend) y lint + typecheck + build (frontend) |
| Diseño visual | Oscuro por defecto con tema claro según el sistema; definido en [`design.md`](design.md) |
| Legal | Política de privacidad, política de cookies y términos de uso (República Dominicana, Ley 172-13) |
| Uso comercial | **No** está previsto cobrar |
| Repositorio | GitHub **público**. Vercel Hobby no deja colaborar en repos privados (solo despliega commits del dueño); en públicos la colaboración es gratis. Por eso nunca se suben secretos al repo |

### Descartado y por qué

- **JWT para la sesión:** se prefieren sesiones guardadas en la base de datos, porque cerrar sesión o eliminar la cuenta corta el acceso al instante y no hay claves de firma que gestionar.
- **Frontend y backend en dominios separados:** Safari en iPhone bloquea las cookies entre dominios y el login fallaría.
- **Supabase Auth:** el equipo prefiere construir el login propio para aprender y no depender del proveedor.
- **Sin ningún límite de uso:** las cuotas de Gemini y YouTube son **por proyecto**; un solo usuario podría agotarlas para todos (YouTube permite ~100 búsquedas al día en total).
- **Bloquear la cuenta tras varios fallos de login:** permitiría a cualquiera bloquear la cuenta de otro sabiendo su email. Se limita por email + IP con esperas.
- **Esperar al reloj para generar la ficha:** el usuario vería «En cola» hasta un minuto sin que pase nada.
- **Un único tick que lo hace todo:** si Gemini tarda, los recordatorios se retrasan o la función se corta. Se separa en tres tareas.
- **Usar la base de datos de producción para desarrollar:** riesgo de borrar o ensuciar datos reales.
- **Sesiones de estudio y selección de conceptos:** sustituidas por un recordatorio diario simple.
- **Explicación por niveles, preguntas de repaso, conceptos relacionados, categorías y etiquetas:** fuera, porque la ficha es una pasada breve.
- **Editar o regenerar conceptos:** el Cuaderno solo permite buscar y eliminar. Sí se permite **reintentar** una ficha que falló.
- **Resend:** requiere dominio propio; se usará cuando exista.
- **Claude Code como motor de IA en producción:** la IA necesita su propia API; la suscripción de Claude no la incluye.
- **Ollama / modelo local:** requiere una computadora encendida.
- **Cron de Vercel Hobby y GitHub Actions como reloj:** frecuencia o cuota insuficientes.

---

## 3. Alcance del MVP

### Incluido

| Área | Funcionalidad |
|---|---|
| Cuenta | Registro con verificación por código, login, logout, recuperar contraseña, cambiar idioma, eliminar cuenta y datos |
| Idioma | Interfaz detectada del dispositivo + elección es/en |
| Captura | Crear conceptos por texto y por atajo de Siri |
| IA | Ficha breve generada al momento; panel de carga; botón **Reintentar** si falla |
| Videos | 2 videos con miniatura y título, uno al lado del otro; al hacer clic abren YouTube |
| Cuaderno | Listado, búsqueda y eliminación de conceptos |
| Recordatorios | Hora diaria + días de la semana; notificación push |
| Límites | Límite diario suave por usuario con mensaje claro al alcanzarlo |
| Instalación | PWA instalable en iPhone y usable en computadora |
| Legal | Privacidad, cookies y términos, en es/en |

### Fuera del MVP

- Login con Google u otros proveedores.
- Planes o límites distintos por usuario.
- Reutilizar fichas entre usuarios (hoy solo se reutilizan los videos).
- Dominio propio y correos con Resend.
- Repaso espaciado, cuestionarios, sesiones de estudio.
- App nativa de iOS.
- Más idiomas.

---

## 4. Arquitectura

```
[PWA React/TS/Vite]  ──HTTPS + cookie──►  [FastAPI en Vercel /api]
        ▲                                     │ SQLAlchemy
        │ Web Push                            ▼
[Atajo de Siri] ──HTTPS + token──►     [PostgreSQL en Supabase]
                                              │ pg_cron
                                              ▼
                              POST /internal/jobs       (cada minuto, respaldo)
                              POST /internal/reminders  (cada minuto)
                              POST /internal/cleanup    (una vez al día)

  Al crear un concepto, la PWA llama a POST /concepts/{id}/process, que genera la ficha al momento:
                                       ├─► Gemini API (ficha)
                                       └─► YouTube Data API (videos)
                    FastAPI ──SMTP──► Gmail del proyecto (códigos y recuperación)
```

### Cómo se usan PostgreSQL, Supabase y SQLAlchemy

| Pieza | Papel |
|---|---|
| **PostgreSQL** | Motor de base de datos: tablas y datos |
| **Supabase** | Aloja ese PostgreSQL (panel web) y aporta `pg_cron` |
| **SQLAlchemy** | Librería con la que FastAPI lee y escribe usando clases de Python |
| **Alembic** | Migraciones: historial versionado de cambios en las tablas |

- El backend se conecta con `DATABASE_URL` a través del **pooler de Supabase** (modo transacción, puerto 6543), necesario en funciones serverless.
- La **API automática de Supabase se desactiva** y las tablas no tienen acceso público: **solo el backend toca la base de datos**.
- El aislamiento entre usuarios se hace en el backend: **toda consulta filtra por `user_id`** mediante una capa de acceso común.
- El código no depende de Supabase: cambiar de proveedor de PostgreSQL es cambiar `DATABASE_URL`.

### 4.1 Entornos

| Entorno | Base de datos | Quién lo usa |
|---|---|---|
| Local | PostgreSQL 16 en Docker (`docker compose up`) | Cada desarrollador; los tests del CI usan el mismo tipo de base |
| Pruebas | Proyecto Supabase **compabook-dev** | Previews de Vercel (una URL por PR) |
| Producción | Proyecto Supabase **compabook-prod** | La app publicada; el único con `pg_cron` activo |

---

## 5. Flujos clave

### 5.1 Registro e idioma

1. La web arranca en el **idioma del dispositivo** (`navigator.language`): inglés si empieza por `en`, español en otro caso.
2. En el registro se pide email, contraseña e **idioma (Español / English)**, preseleccionado con el del dispositivo.
3. Junto al selector, una nota breve:
   - es: «Puedes escribir tus conceptos en cualquier idioma; te los explicaremos en el idioma que elijas.»
   - en: «You can write your concepts in any language; we'll explain them in the language you choose.»
4. Se envía un **código de 6 dígitos** al correo; la cuenta queda activa al introducirlo. La pantalla recuerda **revisar la carpeta de spam**.
5. El idioma se puede cambiar en Ajustes. Las fichas ya generadas se quedan en su idioma original.

### 5.2 Captura y ficha

1. Guardar el concepto (**siempre primero**) y crear su trabajo en la cola.
2. El frontend llama de inmediato a `POST /concepts/{id}/process`, que genera la ficha en esa misma petición.
3. Gemini devuelve una **respuesta estructurada** en el idioma del usuario; se valida y se guarda.
4. Obtener 2 videos: **reutilizar** si ya se buscó ese concepto en ese idioma; si no, buscar en YouTube y guardar en caché.
5. Si algo falla, el reloj lo reintenta automáticamente; al agotar intentos, se muestra **Reintentar**.
6. Si la ficha se guardó pero fallaron los videos, el concepto se completa sin videos; reintentar nunca vuelve a llamar a Gemini si la ficha ya existe.

Estados: `pending` → `processing` → `completed` | `failed`.

**Panel de carga (obligatorio).** Mientras se genera la ficha, la interfaz nunca debe verse congelada:
- El concepto aparece al instante en el Cuaderno con su estado.
- Panel animado por etapas: «En cola» → «Escribiendo la explicación» → «Buscando videos» → «¡Listo!».
- El frontend consulta el estado periódicamente y se actualiza solo.
- La app sigue siendo usable mientras tanto.
- Si falla, mensaje claro y botón **Reintentar**.

### 5.3 Recordatorios

1. Con la PWA instalada (en iPhone, Web Push requiere iOS 16.4+ y la app en la pantalla de inicio), el usuario activa las notificaciones **con un botón**.
2. Elige **hora** y **días de la semana**; la zona horaria se toma del dispositivo.
3. El reloj envía la notificación cuando toca (con hasta 2 horas de margen si hubo una caída), p. ej.: «Tienes 12 conceptos en tu Cuaderno — repasa "CI/CD"» (uno al azar).
4. Si el Cuaderno está vacío no se envía nada. Tocarla abre el concepto sugerido.

### 5.4 Atajo de Siri

- Cada usuario genera un **token personal revocable** en Ajustes (se guarda solo su hash).
- El atajo dicta el texto y hace `POST` al backend con ese token.
- Se entrega una guía paso a paso para crear el atajo, con el aviso de **no compartir el atajo**: lleva el token dentro.

### 5.5 Límite diario

- Cada usuario puede crear hasta **30 conceptos** y pedir **10 reintentos** al día (valores configurables).
- Eliminar conceptos no devuelve cupo.
- Al alcanzarlo, la app y Siri responden con un mensaje claro en el idioma del usuario: «Has llegado al límite de hoy; vuelve mañana».

---

## 6. Modelo de datos (resumen)

| Tabla | Contenido |
|---|---|
| `users` | Email, hash de contraseña, idioma, zona horaria, email verificado, fechas |
| `sessions` | Sesiones abiertas (hash del token, caducidad, último uso) |
| `email_codes` | Códigos de verificación y recuperación (hash, propósito, caducidad, intentos) |
| `rate_limit_events` | Registro de intentos para límites (login, envío de códigos, conceptos y reintentos diarios) |
| `concepts` | Título (lo que escribió el usuario), idioma de la ficha, origen (app/siri), propietario |
| `concept_cards` | Ficha generada: qué es, para qué sirve, ejemplo, clave de caché |
| `video_cache` | Videos por clave de concepto + idioma, compartidos para reutilizar |
| `processing_jobs` | Cola de trabajos (uno por concepto): estado, etapa, intentos, errores |
| `reminder_settings` | Activo, hora, días, último envío (la zona horaria está en `users`) |
| `push_subscriptions` | Dispositivos suscritos a notificaciones |
| `api_tokens` | Tokens personales para Siri (hash) |

Detalle en [`diseno-tecnico.md`](diseno-tecnico.md).

---

## 7. Contenido de la ficha

- Idioma: el del usuario (`es` o `en`), sin importar en qué idioma se escribió el concepto.
- Secciones: **qué es**, **para qué sirve**, **ejemplo**. Breve: se lee en un par de minutos.
- **Los videos no los inventa la IA**: vienen de la YouTube Data API.
- Videos: 2 tarjetas **una al lado de la otra** (apiladas en móvil), con **miniatura y título debajo**; al hacer clic se abre YouTube en una pestaña nueva.
- Todo el contenido de la IA se muestra como **texto** (nunca como HTML).

---

## 8. Pantallas

- **Bienvenida / Login / Registro / Verificar código / Recuperar contraseña.**
- **Inicio:** campo para añadir un concepto y los últimos conceptos.
- **Cuaderno:** buscador y lista; eliminar.
- **Ficha:** qué es, para qué sirve, ejemplo, 2 videos; panel de carga mientras se genera.
- **Ajustes:** idioma, recordatorios (hora y días), notificaciones, token de Siri, cerrar sesión, eliminar cuenta.
- **Legal:** privacidad, cookies, términos.

Diseño visual: [`design.md`](design.md). Base oscura inspirada en Morphic, adaptada a lectura: texto de lectura a 16px, gris más claro dentro de las fichas, colores de estado contenidos y tema claro.

---

## 9. Estructura del repositorio

```
/
├── CLAUDE.md            instrucciones para Claude Code
├── frontend/            React + TS + Vite (PWA)
├── backend/
│   ├── app/{api,models,repositories,services,workers}/
│   ├── alembic/         migraciones
│   └── tests/
├── docs/
├── .github/workflows/   CI (lint, tests, build)
├── docker-compose.yml   PostgreSQL local
├── .gitignore
└── README.md
```

---

## 10. Seguridad y restricciones

1. Contraseñas con **argon2**; nunca en texto plano ni en logs.
2. Sesión en cookie `httpOnly`, `Secure`, `SameSite=Lax`; protección CSRF en peticiones que modifican datos.
3. Códigos de email y tokens se guardan **hasheados**, caducan y tienen límite de intentos.
4. Límite de intentos por email + IP en login, registro y envío de códigos, **con esperas en vez de bloquear la cuenta**.
5. **Toda consulta filtra por `user_id`**; un **test automático** con dos cuentas comprueba que nadie ve datos ajenos.
6. Secretos solo en variables de entorno del backend; nunca en el frontend ni en GitHub.
7. Guardar el concepto antes de llamar a la IA.
8. Manejar errores de cuota de Gemini y YouTube (429) con reintentos y espera.
9. Límite diario por usuario y título de máximo 200 caracteres (cuotas compartidas y coste del prompt).
10. El contenido generado por la IA se muestra como texto, nunca como HTML.
11. **Privacidad:** el nivel gratuito de Gemini puede usar el contenido para mejorar productos de Google; se informa en la política de privacidad.
12. El usuario puede **eliminar su cuenta y todos sus datos**.

---

## 11. Plan por fases

| Fase | Contenido | Estado |
|---|---|---|
| 1. Análisis | Revisión de contexto, diseño y entorno | ✅ |
| 2. Diseño técnico | Datos, API, flujos, criterios | ✅ (revisado) |
| 3. Aprobación | Revisión del equipo | ✅ (PR #1, 2026-10-22) |
| 4. Fundamentos y prueba de riesgos | Estructura, CI, Docker local, FastAPI, SQLAlchemy + Alembic, frontend base con i18n y tema, despliegue en Vercel. **Prueba de concepto** de lo que puede tumbar la arquitectura: FastAPI bajo `/api` en Vercel, cookie en Safari con la PWA instalada, push al iPhone y `pg_cron` → `pg_net` → Vercel | |
| 5. Cuentas | Registro, verificación por código, login, recuperación, idioma, eliminar cuenta, límites de intentos | |
| 6a. Cuaderno + ficha | Crear concepto, ficha con Gemini al momento, búsqueda y eliminación, límite diario | |
| 6b. Cola y videos | Cola de respaldo, videos con caché, panel de carga, reintentar | |
| 7. Recordatorios | Ajustes de hora y días, push, envío desde el reloj | |
| 8. Siri | Tokens personales, endpoint y guía del atajo | |
| 9. Legal y publicación | Textos legales es/en, pruebas en Windows e iPhone, despliegue | |

---

## 12. Pendientes

- [x] Nombre del producto: **CompaBook**.
- [ ] Crear el Gmail del proyecto (envíos y contacto legal) y su contraseña de aplicación.
- [ ] Crear los proyectos Supabase `compabook-dev` y `compabook-prod`.
- [ ] Anotar los límites reales de Gemini al crear la clave en AI Studio y ajustar el límite diario por usuario.
- [ ] Verificar si Supabase gratis **pausa** el proyecto por inactividad aunque `pg_cron` esté activo.
- [ ] Verificar qué **copias de seguridad** incluye Supabase gratis; si no hay, programar un `pg_dump` periódico.
- [ ] Revisión de los textos legales por alguien con conocimiento jurídico antes de abrir al público.
