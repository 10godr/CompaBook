# CompaBook

> **CompaBook**: tu compañero para entender conceptos rápido.

Una app web para entender conceptos rápido. Escribes (o le dictas a Siri) algo como «CI/CD», y una IA te explica en tu idioma qué es, para qué sirve y un ejemplo, con 2 videos de YouTube para profundizar. Todo queda guardado en tu Cuaderno, y puedes elegir a qué hora y qué días quieres que te recuerde repasarlo.

Multiusuario, en español e inglés. Todavía está en fase de diseño, sin código.

## Stack

- **Frontend:** React + TypeScript + Vite (PWA)
- **Backend:** Python + FastAPI
- **Base de datos:** PostgreSQL en Supabase, con SQLAlchemy y Alembic
- **Login:** propio (email + contraseña, verificación por código)
- **IA:** Gemini API
- **Videos:** YouTube Data API
- **Correos:** Gmail (SMTP)
- **Hosting:** Vercel; tareas programadas con `pg_cron` de Supabase

## Cómo trabajamos

- Una rama por tarea (`docs/...`, `feat/...`, `fix/...`).
- Se integra a `main` con Pull Request revisado por el otro.
- Commits pequeños y en español.

## Documentación

- [`docs/contexto.md`](docs/contexto.md): qué es el proyecto, decisiones, alcance y plan por fases
- [`docs/diseno-tecnico.md`](docs/diseno-tecnico.md): base de datos, login, API, flujo de la IA, textos legales y criterios de aceptación
- [`docs/design.md`](docs/design.md): referencia visual (colores, tipografía, componentes)
