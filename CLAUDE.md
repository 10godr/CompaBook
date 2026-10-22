# CompaBook — Instrucciones para Claude Code

App web multiusuario (PWA) para entender conceptos rápido: el usuario escribe un concepto, Gemini genera una ficha breve en su idioma (es/en) con 2 videos de YouTube, y todo se guarda en su Cuaderno con recordatorios por push.

## Antes de nada

Lee los documentos en este orden; si se contradicen, manda el primero:

1. `docs/contexto.md`: producto, decisiones, alcance, fases.
2. `docs/diseno-tecnico.md`: datos, API, procesamiento, entornos, criterios de aceptación.
3. `docs/design.md`: diseño visual y tokens.

Si una petición choca con una decisión de `contexto.md`, dilo antes de actuar.

## Reglas de trabajo

- **No escribas código sin aprobación explícita.** Primero analiza, plantea dudas y presenta un plan.
- Se trabaja por fases (`contexto.md` §11); no adelantes trabajo de fases futuras.
- Una rama por tarea (`docs/...`, `feat/...`, `fix/...`), PR a `main` revisado por el otro miembro. Commits pequeños y **en español**.
- No hagas commit ni push sin que te lo pidan.
- El equipo está aprendiendo: explica las decisiones relevantes, en español.
- Al cerrar una fase, documenta los archivos modificados, las pruebas, la configuración necesaria y los pendientes.
- Si cambia una decisión, actualiza primero `contexto.md` y luego los demás documentos.

## Stack

- Frontend: React + TypeScript + Vite (PWA), `react-i18next`, tema oscuro/claro con tokens de `design.md`.
- Backend: Python + FastAPI, SQLAlchemy 2.0 (`Mapped[...]`), Alembic, `psycopg` 3, `pwdlib` (argon2id), `pywebpush`.
- Base de datos: PostgreSQL (Docker en local, Supabase en preview/producción). Sin Supabase Auth ni Data API.
- Hosting: Vercel, frontend y backend en el mismo dominio (`/api`).
- Servicios detrás de interfaces: `AIProvider` (Gemini), `EmailProvider` (Gmail SMTP), YouTube, Push; en los tests se usan implementaciones falsas.

## Reglas técnicas que no se rompen

- Toda consulta filtra por el `user_id` de la sesión, a través de los repositorios. Nunca aceptes `user_id` del cliente. Un recurso ajeno responde 404.
- Guarda el concepto **antes** de llamar a la IA.
- Secretos solo en variables de entorno del backend; nunca en el frontend, en el repo ni en logs.
- No registres contraseñas, códigos, tokens, cookies ni el contenido de los conceptos.
- El contenido de la IA se muestra como texto, nunca como HTML.
- Todo `POST/PUT/PATCH/DELETE` con cookie exige la cabecera `X-Requested-With: compabook`.
- Nunca uses la base de datos de producción para desarrollar o probar.

## Comandos (cuando exista el código)

- Base de datos local: `docker compose up -d`
- Migraciones: `cd backend && alembic upgrade head`
- Backend: `cd backend && uvicorn app.main:app --reload`
- Tests y lint del backend: `cd backend && ruff check . && pytest`
- Frontend: `cd frontend && npm run dev` (o `npm run lint`, `npm run build`)
