# Pruebas de riesgo — Fase 4

> Pruebas de concepto de lo que puede tumbar la arquitectura ([`contexto.md`](contexto.md) §11). Cada prueba usa código temporal que se elimina al cerrar la fase.

---

## 1. Cookie de sesión en Safari y en la PWA instalada (iPhone)

**Qué se comprueba:** que la cookie `cb_session` de [`diseno-tecnico.md`](diseno-tecnico.md) §2.1 (`HttpOnly`, `Secure`, `SameSite=Lax`, 30 días, renovación pasadas 24 h) sobrevive en Safari y en la PWA añadida a la pantalla de inicio, con frontend y API en el mismo dominio.

**Código temporal:** `backend/app/poc.py` (`/api/v1/poc/cookie`), `frontend/src/pages/PruebaCookie.tsx` (`/prueba-cookie`), manifest e iconos provisionales.

### Procedimiento

Usar siempre `https://compabook.vercel.app/prueba-cookie` (la preview de Vercel pide inicio de sesión).

| # | Dónde | Pasos | Resultado esperado |
|---|---|---|---|
| A | Safari | Abrir la página, **Crear cookie**, **Ver estado** | `present: true` |
| B | Safari | Cerrar la pestaña, abrirla de nuevo, **Ver estado** | `present: true` |
| C | Safari → Compartir → *Añadir a pantalla de inicio* | Abrir desde el icono. Debe decir «Modo PWA instalada: sí». **Ver estado** | Anotar: en iOS la PWA suele tener almacenamiento separado de Safari |
| D | PWA | **Crear cookie** y **Ver estado** | `present: true` |
| E | PWA | Cerrar la app (deslizar hacia arriba) y abrirla, **Ver estado** | `present: true` |
| F | PWA | **Guardar marca en localStorage**, cerrar y abrir, **Leer marca** | La marca sigue ahí |
| G | PWA | Abrir pasadas 24 h y **Ver estado** | `present: true`, `renewed: true` |
| H | PWA | Abrir pasados 8 días sin usarla y **Ver estado** | `present: true` (el límite de 7 días de Safari afecta a lo que escribe JavaScript, no a `Set-Cookie`) |
| I | PWA | **Borrar cookie**, **Ver estado** | `present: false` |

### Resultados

| # | Resultado | Fecha | Notas |
|---|---|---|---|
| A | | | |
| B | | | |
| C | | | |
| D | | | |
| E | | | |
| F | | | |
| G | | | |
| H | | | |
| I | | | |

**Conclusión:** _pendiente_

---

## 2. Push al iPhone

_Pendiente._

## 3. `pg_cron` → `pg_net` → Vercel

_Pendiente (necesita el proyecto `compabook-prod` de Supabase)._
