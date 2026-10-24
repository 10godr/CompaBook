# Cierre de la Fase 5: Cuentas

Cerrada el 2026-10-23. Entregada en los PR #18 a #23. Verificada en producción (`https://compabook.vercel.app`) con un registro real de un correo invitado: llegó el código al Gmail, se verificó la cuenta, se cerró sesión y se volvió a entrar, sin errores.

## Qué entrega

- **Registro solo por invitación.** Un correo que no está en `allowed_emails` recibe `403 registration_not_allowed`. Las invitaciones se gestionan con SQL en Supabase (no hay panel de administración).
- **Verificación por código** de 6 dígitos enviado por Gmail SMTP. El código se guarda como HMAC-SHA256 con `SECRET_KEY`, ligado al usuario y al propósito; caduca a los 15 minutos, admite 5 intentos y un código nuevo invalida el anterior.
- **Login** con bloqueo escalonado: 5 fallos en 15 minutos bloquean 15 minutos, y el bloqueo se duplica en cada reincidencia hasta 1 hora. Un login correcto lo reinicia. Un correo inexistente tarda lo mismo que uno real (verificación contra un hash falso).
- **Sesión** en base de datos con token opaco (solo se guarda su SHA-256) en la cookie `cb_session` (HttpOnly, Secure, SameSite=Lax, 30 días, renovación deslizante tras 24 h).
- **Recuperar contraseña** por código; al restablecer se cierran todas las sesiones.
- **Perfil:** cambiar idioma (se sincroniza con la cuenta), cambiar contraseña (conserva la sesión actual y cierra las demás) y eliminar la cuenta (borrado en cascada; la invitación se conserva).
- **Suspensión:** `users.disabled_at` corta sesiones al instante, porque se comprueba en cada petición.
- **Límites de intentos** guardados en `rate_limit_events` (ver tabla abajo).
- **Limpieza programada:** `POST /internal/cleanup` borra sesiones y códigos caducados, eventos de límite de más de 2 días y cuentas sin verificar de más de 7 días. Está protegido con `X-Internal-Secret`.
- **Pantallas** en español e inglés: bienvenida, entrar, registro, verificar, recuperar, restablecer y ajustes.

### Límites de intentos

| Cubo | Límite |
|---|---|
| `register_ip` | 10 por hora por IP |
| `email_send` | 5 por hora por correo |
| `login_ip` | 30 por hora por IP |
| `login_fail` / `login_lock` | 5 fallos en 15 min por correo+IP, bloqueo 15 min (se duplica hasta 1 h, memoria de 24 h) |
| `password_check` | 5 comprobaciones en 15 min por usuario (cambiar contraseña, eliminar cuenta) |

Solo se registran los intentos permitidos: los bloqueados no alargan la espera.

## Archivos

### Backend (`backend/`)
- `app/api/`: `auth.py`, `me.py`, `internal.py`, `deps.py`, `validators.py`.
- `app/services/`: `accounts.py` (reglas de negocio), `email.py` (`EmailProvider`, `GmailSmtpProvider`, `ConsoleEmailProvider`), `maintenance.py`.
- `app/repositories/`: `users.py`, `sessions.py`, `email_codes.py`, `rate_limits.py`.
- `app/models/accounts.py` y la migración `0002_cuentas`.
- `app/session_cookie.py`, `app/errors.py` (formato `{"error":{"code","message",...}}`), `app/config.py`, `app/common_passwords.py`.
- `tests/`: `test_registro`, `test_login`, `test_sesion`, `test_recuperacion`, `test_cuenta`, `test_mantenimiento`, `test_email_provider`, más `conftest.py` y `helpers.py`.

### Frontend (`frontend/src/`)
- `api.ts`, `errors.ts`.
- `auth/`: `AuthProvider.tsx`, `context.ts`, `guards.tsx`.
- `pages/`: `Welcome`, `Login`, `Register`, `Verify`, `ForgotPassword`, `ResetPassword`, `Settings`.
- `components/`: `AuthLayout`, `CodeInput`, `TextField` (con `PasswordField`), `ConfirmDialog`, `ChangePasswordForm`, `DeleteAccount`.
- `i18n/es.json` y `en.json` (claves `auth.*` y `settings.*`).
- `test/`: `mockApi.ts`, `render.tsx`, `setup.ts`.

### Otros
- `.github/workflows/ci.yml` (el frontend ahora ejecuta `npm test`), `requirements.txt` (`pwdlib[argon2]`, `email-validator`, `tzdata`).
- Documentación: `contexto.md` y `diseno-tecnico.md` (decisiones, esquema, contrato de la API), `pruebas-riesgo.md`.

## Pruebas

- **Backend:** 180 pruebas con pytest sobre PostgreSQL real; `ruff check` y `ruff format --check` limpios. El reloj se simula con la fixture `clock`, y el correo con un proveedor falso.
- **Frontend:** 79 pruebas con Vitest + Testing Library (flujos completos de acceso, ajustes, `CodeInput`, cliente de la API).
- **Navegador real:** 19 comprobaciones con Chrome automatizado contra la API local (no están en el repo). Encontraron un fallo visual real: los botones del ojo de la contraseña salían como cajas azules por un CSS de las pruebas de la Fase 4; quedó corregido.
- **Producción:** `/api/v1/me` sin sesión da 401; `PATCH /me` sin sesión, 401; `POST /internal/cleanup` sin secreto, 401; un correo no invitado, 403; y el registro real de un correo invitado funcionó de principio a fin.

## Configuración necesaria

Variables de entorno del backend (Vercel y `.env` local; nunca en el repo ni en el chat). Ver `backend/.env.example`.

| Variable | Para qué | Nota |
|---|---|---|
| `SECRET_KEY` | HMAC de los códigos | Si falta, el registro falla con error general |
| `SMTP_USER`, `SMTP_APP_PASSWORD`, `SMTP_HOST`, `SMTP_PORT`, `EMAIL_FROM_NAME` | Envío de correos por Gmail | Si faltan, el registro responde 503 "El envío de correos no está disponible" |
| `INTERNAL_SECRET` | Protege `/internal/cleanup` | Debe coincidir con el secreto guardado en Supabase Vault |
| `COOKIE_SECURE` | Cookie solo por HTTPS | `true` en producción, `false` en local |
| `SESSION_DAYS`, `APP_URL`, `DATABASE_URL(_DIRECT)`, `LOG_LEVEL` | Sesión, enlaces, base de datos y logs | |

Base de datos: la migración `0002_cuentas` se aplicó a `compabook-prod` a mano, con el SQL generado por Alembic en el editor de Supabase. En local, `alembic upgrade head`. Las invitaciones se añaden con:

```sql
insert into allowed_emails (email, note) values ('correo@ejemplo.com', 'Nombre');
```

## Pendientes

- **Programar la limpieza diaria:** crear un trabajo de `pg_cron` que llame a `POST /internal/cleanup` con `X-Internal-Secret` (leído desde Vault). El endpoint ya funciona; falta programarlo.
- **Migraciones fuera de local:** hoy se aplican a mano. Decidir si se automatizan en el despliegue.
- **Textos legales:** la casilla de términos del registro es texto simple, sin enlaces. Se resuelve en la Fase 9.
- **Instalación en el iPhone:** Safari y la PWA instalada no comparten cookies, así que hay que iniciar sesión dentro de la app instalada. Va en la guía de instalación (Fase 9).
- **Cierre de la Fase 4** (a partir del 2026-10-30): prueba H de la cookie, revisar y parar `pg_cron` de prueba, y retirar el código temporal de las pruebas de concepto.
- Pendientes de Supabase en `contexto.md` §12 (pausa por inactividad, copias de seguridad).
