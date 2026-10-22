# Knowledge Hub — Contexto del proyecto para Claude Code

> Documento de contexto consolidado a partir de la conversación de diseño. Es la referencia principal para desarrollar el MVP con Claude Code.
> **Estado:** diseño funcional y técnico decidido. Aún no se ha escrito código.

---

## 0. Instrucciones para Claude Code (leer primero)

1. **No modifiques archivos todavía.** Primero analiza este documento, el entorno y la referencia de frontend que te proporcione el usuario.
2. **Plantea dudas antes de desarrollar.** Si algo es ambiguo, pregunta; no tomes decisiones importantes por tu cuenta.
3. **Presenta un plan de implementación** (entidades, endpoints, servicios, variables de entorno, orden de trabajo) y espera aprobación explícita.
4. **Avisa justo antes de empezar a implementar.**
5. **Trabaja por fases y funcionalidades**, probando cada parte antes de continuar. Commits pequeños.
6. **Al entregar cada fase**, documenta: archivos modificados, pruebas realizadas, configuración necesaria y pendientes reales.
7. El usuario está aprendiendo: explica las decisiones relevantes de forma clara.

---

## 1. Visión del producto

Aplicación **personal** de aprendizaje (potencialmente multiusuario en el futuro) donde el usuario:

1. **Captura** un concepto (por texto o dictado con Siri), p. ej. «CI/CD».
2. El concepto se **guarda inmediatamente**, aunque la IA falle o tarde.
3. Un agente de IA **genera automáticamente una ficha de aprendizaje**: explicación, usos, ejemplo práctico, conceptos relacionados, recursos (videos en español) y preguntas de repaso.
4. El usuario **selecciona qué estudiar** y **programa sesiones manualmente**.
5. Recibe una **notificación push** que lo lleva a su sesión con los conceptos seleccionados.

Estilo de producto: herramienta personal de conocimiento, no plataforma educativa tradicional.

---

## 2. Decisiones tomadas

| Tema | Decisión |
|---|---|
| Plataforma | **PWA** instalable en iPhone y usable en computadora (Windows) |
| Agente IA | **Generación automática** de fichas al guardar un concepto |
| Proveedor IA | **Gemini API, nivel gratuito** (proveedor intercambiable en el diseño) |
| Recordatorios | **Notificaciones push propias** de la PWA, enviadas desde el servidor |
| Uso | Personal ahora; arquitectura preparada para multiusuario |
| Estudio | **Selección y horarios manuales** (sin repaso espaciado en el MVP) |
| Voz | **Atajo de Siri** (Apple Shortcuts) que envía el concepto al backend |
| Frontend | Lo desarrolla el usuario aparte con Claude Code **a partir de una referencia visual propia** |
| Backend | **Python + FastAPI** |
| BD y auth | **Supabase** (PostgreSQL + autenticación + RLS) |
| Videos | **YouTube Data API**, priorizando español |
| Repositorio | GitHub **privado** inicialmente (el usuario decidirá luego si lo hace público) |
| Herramientas de desarrollo | Claude Code (desarrollo/integración) y Gemini Pro (consulta, revisión, investigación) |
| Hosting | **Vercel** (Hobby) para la PWA y para FastAPI como funciones serverless |
| Scheduler / worker | **Supabase `pg_cron` + `pg_net`**: cada minuto llama a `POST /internal/tick` (protegido con secreto), que procesa jobs, reintenta fallos y envía push |
| Sistema de diseño | Estilo Morphic (`docs/design.md`) adaptado: cuerpo de lectura a 16px, gris más claro en fichas y **colores de estado contenidos** (error/éxito) |
| Profundidad de fichas | De lo básico hasta un ejemplo técnico real |

### Decisiones explícitamente descartadas y por qué

- **Claude Code como motor de IA en producción: NO.** Claude Code construye el agente, pero el agente debe tener su propio mecanismo de ejecución (API). La suscripción de Claude no incluye API gratuita; la API de Anthropic se factura aparte. Ejecutarlo desde la computadora del usuario obligaría a mantenerla encendida.
- **Gemini Pro (suscripción) ≠ Gemini API.** Son servicios distintos; se usará la cuota gratuita de la API.
- **Ollama / modelo local: NO en el MVP.** Requiere la computadora encendida y complica el uso desde iPhone.
- **Sistema multiagente autónomo: NO.** Basta un flujo definido con un modelo y herramientas concretas.
- **Temporizadores JavaScript en cliente para recordatorios: NO.** Los recordatorios deben ejecutarse en el servidor.
- **Cron de Vercel Hobby: NO** como base de recordatorios (frecuencia máxima diaria, precisión limitada).
- **GitHub Actions programado: NO.** En repo privado la cuota gratuita (2.000 min/mes) no alcanza para ejecuciones cada pocos minutos, y los schedules suelen retrasarse.

---

## 3. Alcance del MVP

### Incluido

| Área | Funcionalidad |
|---|---|
| Captura | Crear conceptos por texto y mediante atajo de Siri |
| Biblioteca | Consultar, buscar, filtrar, ordenar, editar y eliminar conceptos |
| IA | Generar fichas automáticamente; reintentar si falla |
| Recursos | Videos de YouTube en español con enlaces reales y verificables |
| Organización | Categorías, etiquetas y estado de aprendizaje |
| Estudio | Seleccionar conceptos y programar sesiones manualmente |
| Recordatorios | Crear horarios y recibir notificaciones push de la PWA |
| Instalación | PWA instalable en iPhone y usable en computadora |
| Privacidad | Biblioteca privada mediante autenticación |

### Fuera del MVP (segunda etapa o más adelante)

- Repaso espaciado basado en algoritmos de memoria.
- Cuestionarios adaptativos.
- Sincronización (bidireccional) con Apple Recordatorios.
- App nativa de iOS.
- Integración nativa avanzada con Siri.
- Sistema multiusuario completo con roles y administración.
- Generación de podcasts, audio o video propios.
- Sistemas de agentes autónomos colaborativos.

---

## 4. Arquitectura

```
[PWA React/TS/Vite]  ──HTTP──►  [FastAPI backend]  ──►  [Supabase: Postgres + Auth]
        ▲                            │
        │ push                       ├──► Gemini API (fichas, salida estructurada)
        │                            ├──► YouTube Data API (videos reales)
[Atajo de Siri] ──HTTP──►            └──► Worker/scheduler: tareas pendientes,
                                          reintentos y envío de Web Push
```

- **Frontend:** React + TypeScript + Vite (PWA). Diseño visual a cargo del usuario con su referencia.
- **Backend:** Python + FastAPI — autenticación, reglas de negocio, API, coordinación de tareas, llamadas a servicios externos.
- **Supabase:** PostgreSQL, usuarios, permisos (Row Level Security).
- **Procesamiento y notificaciones:** en infraestructura de servidor, **sin depender de que la PWA o la computadora estén abiertas**.
- **Contrato de API** entre frontend y backend definido desde el principio para que evolucionen por separado.
- **Proveedor de IA detrás de una interfaz/abstracción** (p. ej. `AIProvider`) para poder cambiar Gemini por otro en el futuro.

---

## 5. Flujos clave

### 5.1 Captura y generación de ficha

1. Guardar el concepto en BD (**siempre primero**).
2. Crear una tarea de generación (tabla de jobs).
3. Solicitar a Gemini una **respuesta estructurada** (JSON con esquema).
4. **Validar** la respuesta y guardarla como ficha (versionada).
5. Buscar videos reales en YouTube (español) y guardarlos.
6. Mostrar el resultado en la biblioteca.
7. Permitir **reintentar** si algo falla.

Estados de la ficha/tarea: `pending` → `processing` → `completed` | `failed`.

**Requisito de experiencia: panel de carga (obligatorio).** Mientras la ficha se genera (puede tardar hasta ~1 minuto), la interfaz **nunca debe verse congelada**:
- El concepto aparece al instante en la biblioteca con su estado visible.
- La ficha muestra un panel de carga animado y vivo (skeleton/progreso por etapas: «En cola» → «Generando explicación» → «Buscando videos» → «Listo»), con textos cercanos y en español.
- El frontend consulta el estado periódicamente (polling) y se actualiza solo al completarse, sin recargar.
- La app sigue siendo usable mientras tanto (se puede navegar y añadir más conceptos).
- Si falla, se muestra un mensaje claro y el botón de reintentar.

### 5.2 Notificaciones programadas

1. Instalar la PWA en el iPhone (pantalla de inicio; Web Push soportado desde iOS 16.4).
2. Solicitar permiso de notificaciones **mediante una acción explícita del usuario** (botón).
3. Registrar la suscripción push (Web Push / VAPID) en el backend.
4. Guardar sesiones con fecha, hora, zona horaria y conceptos.
5. Un proceso programado en el servidor envía la notificación cuando corresponde; al tocarla, abre la sesión.

No se promete precisión al segundo; depende del proveedor de ejecución y del sistema push.

### 5.3 Atajo de Siri

- Atajo de Apple Shortcuts que dicta un texto y hace un `POST` autenticado al backend para crear el concepto.
- Requiere definir un mecanismo de autenticación apto para el atajo (p. ej. token personal revocable). **Pendiente de diseñar.**

---

## 6. Modelo de datos inicial (PostgreSQL)

| Tabla | Contenido |
|---|---|
| `users` | Cuenta, preferencias, zona horaria, configuración de estudio |
| `concepts` | Título, descripción original, categoría, etiquetas, estado de aprendizaje, fecha de creación, propietario |
| `concept_content` | Explicación (por niveles), utilidad, ejemplo real, conceptos relacionados, preguntas de repaso, versión de la ficha |
| `concept_resources` *(sugerida)* | Videos: título, canal, URL, id de YouTube, idioma |
| `study_sessions` | Fecha, hora, zona horaria, estado, conceptos seleccionados (relación N:M con `concepts`) |
| `push_subscriptions` | Suscripciones de dispositivos y estado |
| `processing_jobs` | Tipo de tarea, estado, intentos, errores, timestamps |

Reglas:
- Separar conceptos, contenido y sesiones: un concepto puede estar en varias sesiones sin duplicarse.
- **Cada registro tiene propietario** (`user_id`) y se aplican **permisos a nivel de BD (RLS)** aunque hoy haya un solo usuario.
- Migraciones en `supabase/migrations/`.

---

## 7. Contenido de la ficha generada por IA

- **Profundidad:** desde lo básico hasta un ejemplo técnico real, sin asumir conocimientos avanzados (opción recomendada; confirmar con el usuario).
- Secciones: explicación por niveles, para qué sirve/usos, ejemplo de uso real, conceptos relacionados, preguntas de repaso.
- Idioma: español.
- **Los videos NO los inventa la IA**: deben provenir de resultados reales de la YouTube Data API. Nunca mostrar como verificado un enlace sugerido por el modelo.

---

## 8. Pantallas (referencia funcional; el diseño visual lo aporta el usuario)

- **Inicio:** conceptos pendientes, próxima sesión, acceso rápido para añadir concepto, resumen de aprendizaje.
- **Biblioteca:** buscador, filtros por categoría y estado, orden por fecha o nombre, acciones editar/eliminar/regenerar.
- **Ficha:** explicación por niveles, ejemplo real, videos y recursos, preguntas de repaso, botón «marcar como aprendido».
- **Planificador:** seleccionar conceptos, programar fecha y hora, activar/cancelar recordatorios, historial de sesiones.

---

## 9. Estructura de repositorio orientativa

```
knowledge-hub/
├── frontend/
│   ├── src/{components,pages,services,types}/
│   ├── public/
│   └── package.json
├── backend/
│   ├── app/{api,models,services,workers}/
│   ├── tests/
│   └── requirements.txt
├── supabase/migrations/
├── docs/
├── .gitignore
├── .env.example
└── README.md
```

No es necesario crear todos los directorios desde el primer día. El README debe explicar: ejecución local, variables de entorno, migraciones y despliegue.

---

## 10. Reglas de seguridad y restricciones (obligatorias)

1. **Comprobar los límites y modelos disponibles de Gemini API (nivel gratuito) antes de implementar**; no asumir cuota ilimitada. Manejar errores de cuota (429) con reintentos/backoff.
2. **Guardar el concepto antes de llamar a la IA**; gestionar errores sin perder información.
3. **La clave de Gemini (y cualquier secreto) solo en el backend**: nunca en el frontend ni en GitHub. Usar `.env` + `.env.example`.
4. El repositorio no contendrá contraseñas, claves privadas, tokens ni credenciales de BD (aunque sea privado).
5. Tener en cuenta que el **nivel gratuito de Gemini puede usar el contenido para mejorar productos de Google** (privacidad).
6. Respetar cuotas y condiciones de la YouTube Data API.
7. Minimizar costos: priorizar servicios gratuitos. La IA gratuita no implica que alojamiento, scheduler, push o YouTube sean gratis; elegir proveedores con capa gratuita y señalar cualquier posible costo antes de adoptarlo.

---

## 11. Plan de implementación por fases

1. **Análisis** (sin modificar archivos): revisar este documento, la referencia de frontend, el entorno y herramientas.
2. **Diseño técnico:** entidades, endpoints (contrato de API), servicios externos, variables de entorno, flujo de procesamiento, criterios de aceptación.
3. **Aprobación:** plan completo + dudas + cambios previstos. Aviso explícito antes de implementar.
4. **Fundamentos:** repositorio, frontend base, backend base, conexión con Supabase, auth.
5. **Biblioteca:** CRUD, búsqueda, filtros de conceptos.
6. **IA:** generación con Gemini, búsqueda de videos, manejo de errores y reintentos.
7. **Estudio y notificaciones:** sesiones, suscripciones push, scheduler en servidor.
8. **Siri:** endpoint + autenticación del atajo + guía para crear el atajo.
9. **Pruebas y publicación:** verificar en Windows e iPhone, documentar y desplegar.

---

## 12. Decisiones pendientes (resolver con el usuario antes o durante la fase de diseño técnico)

- [x] **Hosting del backend y del worker/scheduler:** Vercel + Supabase `pg_cron`.
- [x] **Hosting del frontend PWA:** Vercel.
- [x] **Modelo concreto de Gemini:** `gemini-3.8-flash` con respaldo `gemini-3.5-flash-lite` (ver `diseno-tecnico.md`).
- [x] **Profundidad de explicaciones:** de lo básico a ejemplo técnico real.
- [ ] **Autenticación del atajo de Siri** (token personal, etc.).
- [x] **Esquema JSON de la ficha y contrato de API:** en `diseno-tecnico.md`.
- [x] **Criterios de aceptación:** en `diseno-tecnico.md`.
- [ ] Identidad visual: **la define el usuario** con su referencia (no decidir).
- [ ] Visibilidad del repo: **privado**; el usuario lo gestionará después (no decidir).
