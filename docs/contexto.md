# CompaBook — Contexto del proyecto

> Referencia principal del proyecto para el equipo (Diego Rodriguez y Emile Rosario) y para Claude Code.
> **Estado:** diseño funcional y técnico decidido; replanteado a multiusuario el 2026-10-23. Aún no se ha escrito código.
> Nombre del producto: **CompaBook**. La sección donde el usuario guarda sus conceptos se llama «Cuaderno» (*Notebook* en inglés).

---

## 0. Forma de trabajo

1. **No se escribe código sin aprobación explícita.** Primero se analiza, se plantean dudas y se presenta un plan.
2. **Se trabaja por fases**, probando cada parte antes de continuar.
3. **Git:** una rama por tarea (`docs/...`, `feat/...`, `fix/...`) y se integra a `main` mediante Pull Request revisado por el otro miembro. Commits pequeños y en español.
4. **Al cerrar cada fase** se documenta: archivos modificados, pruebas realizadas, configuración necesaria y pendientes reales.
5. El equipo está aprendiendo: las decisiones relevantes se explican.

---

## 1. Visión del producto

Aplicación web **multiusuario** para entender conceptos rápido. No es un curso ni sigue lecciones: es una pasada breve para entender algo y guardarlo.

1. El usuario se **registra** (email + contraseña, verificado con código) y elige su **idioma: español o inglés**.
2. **Escribe o dicta (Siri)** un concepto, p. ej. «CI/CD». Puede escribirlo en cualquier idioma.
3. El concepto se **guarda inmediatamente**, aunque la IA falle o tarde.
4. Un agente de IA genera, **en el idioma del usuario**, una ficha breve:
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
| Sesión | **Cookie segura `httpOnly`** con token de sesión guardado (hasheado) en la base de datos; sin cookies de analítica ni publicidad |
| Base de datos | **PostgreSQL alojado en Supabase**, accedido con **SQLAlchemy** y migraciones con **Alembic** |
| Uso de Supabase | Solo como **base de datos** y **`pg_cron`** (reloj). No se usa su Auth ni su API automática |
| Backend | **Python + FastAPI** |
| Frontend | **React + TypeScript + Vite** (PWA) |
| Hosting | **Vercel** (Hobby), subdominio `*.vercel.app`. Sin dominio propio por ahora. Frontend y backend en el **mismo proyecto y mismo dominio** (el backend en `/api`) para que la cookie de sesión funcione en Safari de iPhone |
| Correos | **Gmail del proyecto** por SMTP con contraseña de aplicación, detrás de `EmailProvider` (migrable a Resend cuando haya dominio) |
| IA | **Gemini API, nivel gratuito**, detrás de `AIProvider` |
| Videos | **YouTube Data API**, 2 videos en el idioma del usuario, **reutilizando** resultados ya buscados |
| Idiomas | Español e inglés, para la interfaz y para el contenido |
| Recordatorios | Notificaciones **Web Push**: una hora al día y días de la semana elegidos por el usuario |
| Voz | **Atajo de Siri** con token personal por usuario |
| Límites de uso | **Ninguno por ahora**; se prueba con pocos usuarios |
| Legal | Política de privacidad, política de cookies y términos de uso (República Dominicana, Ley 172-13) |
| Uso comercial | **No** está previsto cobrar |
| Repositorio | GitHub **privado** |

### Descartado y por qué

- **JWT para la sesión:** se prefieren sesiones guardadas en la base de datos, porque cerrar sesión o eliminar la cuenta corta el acceso al instante y no hay claves de firma que gestionar.
- **Frontend y backend en dominios separados:** Safari en iPhone bloquea las cookies entre dominios y el login fallaría.
- **Supabase Auth:** el equipo prefiere construir el login propio para aprender y no depender del proveedor.
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
| IA | Ficha breve automática; panel de carga; botón **Reintentar** si falla |
| Videos | 2 videos con miniatura y título, uno al lado del otro; al hacer clic abren YouTube |
| Cuaderno | Listado, búsqueda y eliminación de conceptos |
| Recordatorios | Hora diaria + días de la semana; notificación push |
| Instalación | PWA instalable en iPhone y usable en computadora |
| Legal | Privacidad, cookies y términos, en es/en |

### Fuera del MVP

- Login con Google u otros proveedores.
- Límites de uso por usuario.
- Dominio propio y correos con Resend.
- Repaso espaciado, cuestionarios, sesiones de estudio.
- App nativa de iOS.
- Más idiomas.

---

## 4. Arquitectura

```
[PWA React/TS/Vite]  ──HTTPS + cookie──►  [FastAPI en Vercel]
        ▲                                     │ SQLAlchemy
        │ Web Push                            ▼
[Atajo de Siri] ──HTTPS + token──►     [PostgreSQL en Supabase]
                                              │ pg_cron (cada minuto)
                                              ▼
                                     POST /internal/tick
                                       ├─► Gemini API (fichas)
                                       ├─► YouTube Data API (videos)
                                       └─► Web Push (recordatorios)
                    FastAPI ──SMTP──► Gmail del proyecto (códigos y recuperación)
```

### Cómo se usan PostgreSQL, Supabase y SQLAlchemy

| Pieza | Papel |
|---|---|
| **PostgreSQL** | Motor de base de datos: tablas y datos |
| **Supabase** | Aloja ese PostgreSQL (panel web, copias de seguridad) y aporta `pg_cron` |
| **SQLAlchemy** | Librería con la que FastAPI lee y escribe usando clases de Python |
| **Alembic** | Migraciones: historial versionado de cambios en las tablas |

- El backend se conecta con `DATABASE_URL` a través del **pooler de Supabase** (modo transacción, puerto 6543), necesario en funciones serverless.
- La **API automática de Supabase se desactiva** y las tablas no tienen acceso público: **solo el backend toca la base de datos**.
- El aislamiento entre usuarios se hace en el backend: **toda consulta filtra por `user_id`** mediante una capa de acceso común.
- El código no depende de Supabase: cambiar de proveedor de PostgreSQL es cambiar `DATABASE_URL`.

---

## 5. Flujos clave

### 5.1 Registro e idioma

1. La web arranca en el **idioma del dispositivo** (`navigator.language`): inglés si empieza por `en`, español en otro caso.
2. En el registro se pide email, contraseña e **idioma (Español / English)**, preseleccionado con el del dispositivo.
3. Junto al selector, una nota breve:
   - es: «Puedes escribir tus conceptos en cualquier idioma; te los explicaremos en el idioma que elijas.»
   - en: «You can write your concepts in any language; we'll explain them in the language you choose.»
4. Se envía un **código de 6 dígitos** al correo; la cuenta queda activa al introducirlo.
5. El idioma se puede cambiar en Ajustes. Las fichas ya generadas se quedan en su idioma original.

### 5.2 Captura y ficha

1. Guardar el concepto (**siempre primero**).
2. Crear un trabajo en la cola.
3. El reloj (`pg_cron`) llama cada minuto a `/internal/tick`, que pide a Gemini una **respuesta estructurada** en el idioma del usuario.
4. Validar y guardar la ficha.
5. Obtener 2 videos: **reutilizar** si ya se buscó ese concepto en ese idioma; si no, buscar en YouTube y guardar en caché.
6. Si algo falla, reintentar automáticamente; al agotar intentos, mostrar **Reintentar**.

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
3. El reloj envía la notificación cuando toca, p. ej.: «Tienes 12 conceptos en tu Cuaderno — repasa "CI/CD"» (uno al azar).
4. Si el Cuaderno está vacío no se envía nada. Tocarla abre el concepto sugerido.

### 5.4 Atajo de Siri

- Cada usuario genera un **token personal revocable** en Ajustes (se guarda solo su hash).
- El atajo dicta el texto y hace `POST` al backend con ese token.
- Se entrega una guía paso a paso para crear el atajo.

---

## 6. Modelo de datos (resumen)

| Tabla | Contenido |
|---|---|
| `users` | Email, hash de contraseña, idioma, zona horaria, email verificado, fechas |
| `email_codes` | Códigos de verificación y recuperación (hash, propósito, caducidad, intentos) |
| `concepts` | Título, texto original, idioma de la ficha, origen (app/siri), propietario |
| `concept_cards` | Ficha generada: qué es, para qué sirve, ejemplo |
| `video_cache` | Videos por concepto normalizado + idioma, compartidos para reutilizar |
| `processing_jobs` | Cola de trabajos: estado, etapa, intentos, errores |
| `reminder_settings` | Hora, días, zona horaria, activo |
| `push_subscriptions` | Dispositivos suscritos a notificaciones |
| `api_tokens` | Tokens personales para Siri (hash) |

Detalle en [`diseno-tecnico.md`](diseno-tecnico.md).

---

## 7. Contenido de la ficha

- Idioma: el del usuario (`es` o `en`), sin importar en qué idioma se escribió el concepto.
- Secciones: **qué es**, **para qué sirve**, **ejemplo**. Breve: se lee en un par de minutos.
- **Los videos no los inventa la IA**: vienen de la YouTube Data API.
- Videos: 2 tarjetas **una al lado de la otra** (apiladas en móvil), con **miniatura y título debajo**; al hacer clic se abre YouTube en una pestaña nueva.

---

## 8. Pantallas

- **Bienvenida / Login / Registro / Verificar código / Recuperar contraseña.**
- **Inicio:** campo para añadir un concepto y los últimos conceptos.
- **Cuaderno:** buscador y lista; eliminar.
- **Ficha:** qué es, para qué sirve, ejemplo, 2 videos; panel de carga mientras se genera.
- **Ajustes:** idioma, recordatorios (hora y días), notificaciones, token de Siri, cerrar sesión, eliminar cuenta.
- **Legal:** privacidad, cookies, términos.

Diseño visual: [`design.md`](design.md) (estilo Morphic adaptado: lectura a 16px, gris más claro en fichas, colores de estado contenidos).

---

## 9. Estructura del repositorio

```
/
├── frontend/          React + TS + Vite (PWA)
├── backend/
│   ├── app/{api,models,services,workers}/
│   ├── alembic/       migraciones
│   └── tests/
├── docs/
├── .gitignore
└── README.md
```

---

## 10. Seguridad y restricciones

1. Contraseñas con **argon2**; nunca en texto plano ni en logs.
2. Sesión en cookie `httpOnly`, `Secure`, `SameSite=Lax`; protección CSRF en peticiones que modifican datos.
3. Códigos de email y tokens se guardan **hasheados**, caducan y tienen límite de intentos.
4. Límite de intentos en login, registro y envío de códigos para evitar abuso.
5. **Toda consulta filtra por `user_id`**; se prueba con dos cuentas que nadie ve datos ajenos.
6. Secretos solo en variables de entorno del backend; nunca en el frontend ni en GitHub.
7. Guardar el concepto antes de llamar a la IA.
8. Manejar errores de cuota de Gemini y YouTube (429) con reintentos y espera.
9. **Privacidad:** el nivel gratuito de Gemini puede usar el contenido para mejorar productos de Google; se informa en la política de privacidad.
10. El usuario puede **eliminar su cuenta y todos sus datos**.

---

## 11. Plan por fases

| Fase | Contenido | Estado |
|---|---|---|
| 1. Análisis | Revisión de contexto, diseño y entorno | ✅ |
| 2. Diseño técnico | Datos, API, flujos, criterios | ✅ (replanteado) |
| 3. Aprobación | Revisión del equipo | ⏳ |
| 4. Fundamentos | Estructura, FastAPI, SQLAlchemy + Alembic con Supabase, frontend base con i18n, despliegue en Vercel | |
| 5. Cuentas | Registro, verificación por código, login, recuperación, idioma, eliminar cuenta | |
| 6. Cuaderno + IA | Crear concepto, cola, Gemini, videos, panel de carga, reintentar, búsqueda y eliminación | |
| 7. Recordatorios | Ajustes de hora y días, push, envío desde el reloj | |
| 8. Siri | Tokens personales, endpoint y guía del atajo | |
| 9. Legal y publicación | Textos legales es/en, pruebas en Windows e iPhone, despliegue | |

---

## 12. Pendientes

- [x] Nombre del producto: **CompaBook**.
- [ ] Crear el Gmail del proyecto (envíos y contacto legal) y su contraseña de aplicación.
- [ ] Anotar los límites reales de Gemini al crear la clave en AI Studio.
- [ ] Revisión de los textos legales por alguien con conocimiento jurídico antes de abrir al público.
