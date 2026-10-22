# CompaBook

> **CompaBook**: tu compañero para entender conceptos rápido.

Una app web para entender conceptos rápido. Escribes (o le dictas a Siri) algo como «CI/CD», y una IA te explica en tu idioma qué es, para qué sirve y un ejemplo, con 2 videos de YouTube para profundizar. Todo queda guardado en tu Cuaderno, y puedes elegir a qué hora y qué días quieres que te recuerde repasarlo.

Multiusuario, en español e inglés. Todavía está en fase de diseño, sin código.

## Stack

- **Frontend:** React + TypeScript + Vite (PWA), tema oscuro y claro
- **Backend:** Python + FastAPI
- **Base de datos:** PostgreSQL en Supabase (Docker en local), con SQLAlchemy y Alembic
- **Login:** propio (email + contraseña, verificación por código)
- **IA:** Gemini API
- **Videos:** YouTube Data API
- **Correos:** Gmail (SMTP)
- **Hosting:** Vercel; tareas programadas con `pg_cron` de Supabase
- **CI:** GitHub Actions (lint, tests y build en cada PR)

## Cómo trabajamos

- No se escribe código sin un plan aprobado.
- Una rama por tarea (`docs/...`, `feat/...`, `fix/...`).
- Se integra a `main` con Pull Request revisado por el otro y con el CI en verde.
- Commits pequeños y en español.
- Nunca se desarrolla contra la base de datos de producción.

## Documentación

Si dos documentos se contradicen, manda el primero de esta lista:

1. [`docs/contexto.md`](docs/contexto.md): qué es el proyecto, decisiones, alcance y plan por fases
2. [`docs/diseno-tecnico.md`](docs/diseno-tecnico.md): base de datos, login, API, procesamiento, entornos, calidad, textos legales y criterios de aceptación
3. [`docs/design.md`](docs/design.md): diseño visual (colores, tipografía, componentes)

[`CLAUDE.md`](CLAUDE.md) resume las reglas para trabajar con Claude Code.
