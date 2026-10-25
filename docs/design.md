# CompaBook — Diseño visual

> Referencia visual de CompaBook. Se subordina a [`contexto.md`](contexto.md): si algo de aquí contradice una decisión del producto, manda el contexto.
> Punto de partida: el estilo de Morphic (lienzo oscuro, un solo acento azul, Inter, bordes casi invisibles), **adaptado a una app de lectura**. De Morphic se quitó todo lo propio de una galería de imágenes: carruseles horizontales, cuadrículas de imágenes, titulares de 52px, insignias de lanzamiento y texto de cuerpo a 14px en gris oscuro.

---

## 1. Principios

1. **Leer es lo principal.** La ficha se lee en un par de minutos: texto de lectura a 16px, buen interlineado, contraste alto.
2. **Un solo acento.** El azul se reserva para la acción principal, los enlaces y el foco. Los colores de estado existen, pero contenidos: solo en indicadores pequeños y mensajes, nunca como fondo de superficie grande.
3. **Calma.** Superficies planas, sin degradados, casi sin sombras. La jerarquía la dan los niveles de superficie.
4. **Móvil primero.** La app se usa sobre todo como PWA en iPhone; en computadora el contenido se centra con un ancho de lectura cómodo.
5. **Accesible.** Todo texto cumple WCAG AA (4,5:1; 3:1 para texto grande y bordes de controles). Objetivos táctiles de mínimo 44 × 44 px. Respeta `prefers-reduced-motion`.

---

## 2. Tema

- **Oscuro por defecto**, con **tema claro** que se activa según `prefers-color-scheme`.
- En Ajustes: «Sistema / Oscuro / Claro» (se guarda en `localStorage`).
- Se aplica con el atributo `data-theme` en `<html>`; los componentes solo usan tokens, nunca colores sueltos.
- `<meta name="theme-color">` cambia con el tema (`#000000` / `#ffffff`).

---

## 3. Colores

### 3.1 Tema oscuro (por defecto)

| Token | Valor | Uso |
|---|---|---|
| `--bg-canvas` | `#000000` | Fondo de página |
| `--bg-card` | `#212121` | Fichas, tarjetas del Cuaderno, paneles |
| `--bg-raised` | `#292929` | Botón secundario, campos de texto, elementos dentro de una tarjeta |
| `--bg-floating` | `#333333` | Modales, menús, estado pulsado |
| `--text-strong` | `#ffffff` | Títulos, botones, etiquetas importantes |
| `--text-reading` | `#d4d4d4` | **Texto de lectura dentro de la ficha** (el «gris más claro») |
| `--text-muted` | `#a3a3a3` | Texto secundario, metadatos, ayudas |
| `--text-subtle` | `#8a8a8a` | Pistas de campos (*placeholder*), fechas; solo sobre `--bg-canvas` o `--bg-card` |
| `--border` | `rgba(229, 231, 235, 0.12)` | Bordes y separadores de tarjetas |
| `--border-control` | `#767676` | Borde de campos y botones de contorno (3:1) |
| `--icon` | `#a3a3a3` | Iconos |
| `--accent` | `#0066dd` | Fondo del botón principal (texto blanco, ~4,9:1) |
| `--accent-hover` | `#0058c0` | Hover y pulsado del botón principal |
| `--brand` | `#0075ff` | El azul original de Morphic: **solo** logotipo e icono de la app, nunca detrás de texto |
| `--accent-text` | `#4d9bff` | Enlaces y texto azul sobre fondo oscuro |
| `--focus-ring` | `#4d9bff` | Anillo de foco |

### 3.2 Tema claro

| Token | Valor |
|---|---|
| `--bg-canvas` | `#ffffff` |
| `--bg-card` | `#f5f5f5` |
| `--bg-raised` | `#ebebeb` |
| `--bg-floating` | `#ffffff` (con borde y sombra suave) |
| `--text-strong` | `#0a0a0a` |
| `--text-reading` | `#262626` |
| `--text-muted` | `#525252` |
| `--text-subtle` | `#6b6b6b` |
| `--border` | `rgba(0, 0, 0, 0.10)` |
| `--border-control` | `#7a7a7a` |
| `--icon` | `#525252` |
| `--accent` | `#0066dd` |
| `--accent-hover` | `#0058c0` |
| `--accent-text` | `#0066dd` |
| `--focus-ring` | `#0066dd` |

### 3.3 Colores de estado

Solo para el punto o icono del estado, el texto del mensaje y un fondo muy tenue (el color al 12%). Nunca rellenan botones grandes ni tarjetas enteras.

| Estado | Token | Oscuro | Claro | Dónde |
|---|---|---|---|---|
| En proceso | `--status-progress` | `#4d9bff` | `#0066dd` | `pending` / `processing` |
| Listo | `--status-success` | `#3ecf8e` | `#15803d` | `completed`, «¡Listo!» |
| Error | `--status-error` | `#f2555a` | `#c62828` | `failed`, errores de formulario, eliminar |
| Aviso | `--status-warning` | `#f5b544` | `#a15c00` | Límite diario, notificaciones desactivadas |

### 3.4 Reglas

- Nunca se introduce un color fuera de estas tablas.
- El texto de cuerpo nunca usa `--text-subtle`; los grises oscuros de Morphic (`#666`, `#525252`, `#404040`) **no se usan para texto** en tema oscuro porque no llegan al contraste mínimo.
- Los bordes se notan, pero apenas se ven.

---

## 4. Tipografía

- **Inter** para todo (pesos 400, 500, 600 y 700), cargada con `font-display: swap`. Alternativa: `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`.
- **Monoespaciada** para `example_code`: `ui-monospace, "SF Mono", "JetBrains Mono", Consolas, monospace`.
- Tamaños en `rem` para respetar el tamaño de letra del sistema.
- Máximo dos pesos por pantalla, además de los botones.

| Rol | Tamaño | Peso | Interlineado | Tracking | Token | Uso |
|---|---|---|---|---|---|---|
| caption | 12px | 400 | 1.4 | 0 | `--text-caption` | Fechas, canal del video, contadores |
| small | 14px | 400/500 | 1.45 | -0.01em | `--text-small` | Metadatos, ayudas, botones, pestañas |
| body | 16px | 400 | 1.6 | -0.011em | `--text-body` | **Texto de lectura de la ficha** y párrafos |
| body-lg | 18px | 500 | 1.45 | -0.015em | `--text-body-lg` | Campo para añadir un concepto, título de tarjeta |
| heading-sm | 20px | 600 | 1.35 | -0.02em | `--text-heading-sm` | Títulos de sección de la ficha («Qué es») |
| heading | 28px | 700 | 1.2 | -0.03em | `--text-heading` | Título de pantalla, título de la ficha |
| display | 36px (móvil) / 44px (≥ 768px) | 700 | 1.15 | -0.045em | `--text-display` | Solo en Bienvenida |
| code | 14px | 400 | 1.55 | 0 | `--text-code` | Bloque de código del ejemplo |

- El cuerpo siempre va alineado a la izquierda; solo se centran la Bienvenida y los estados vacíos.
- Ancho máximo de lectura de la ficha: **68ch**.

### Titular a dos tonos

El recurso de Morphic que se conserva: dos líneas del mismo tamaño, la primera en `--text-strong` y la segunda en `--text-muted`. Se usa **solo en la Bienvenida** y en los estados vacíos, no en cada pantalla.

- es: «Entiende cualquier concepto» / «en un par de minutos.»
- en: «Understand any concept» / «in a couple of minutes.»

---

## 5. Espaciado, formas y elevación

**Unidad base:** 4px.

| Token | Valor |
|---|---|
| `--space-1` | 4px |
| `--space-2` | 8px |
| `--space-3` | 12px |
| `--space-4` | 16px |
| `--space-5` | 20px |
| `--space-6` | 24px |
| `--space-8` | 32px |
| `--space-10` | 40px |
| `--space-12` | 48px |
| `--space-16` | 64px |

| Radio | Valor | Uso |
|---|---|---|
| `--radius-control` | 8px | Botones, campos, badges |
| `--radius-card` | 12px | Tarjetas del Cuaderno, tarjetas de video, bloque de código |
| `--radius-panel` | 16px | Ficha completa, panel de carga |
| `--radius-modal` | 24px | Modales y hojas inferiores |
| `--radius-full` | 999px | Píldoras de estado, chips de días |

- **Sin sombras** en tema oscuro; la elevación la dan las superficies.
- En tema claro, solo modales y menús llevan `--shadow-float: 0 8px 24px rgba(0, 0, 0, 0.12)`.
- Sin degradados.

---

## 6. Layout

- **Móvil (< 768px):** una columna, margen lateral de 16px, barra de navegación inferior fija.
- **Escritorio (≥ 768px):** contenido centrado con ancho máximo de **720px** (la ficha ocupa como mucho 68ch de texto); la navegación pasa a una barra superior.
- Se respetan las zonas seguras del iPhone: `padding: env(safe-area-inset-top) … env(safe-area-inset-bottom)`, sobre todo en la barra inferior.
- Separación entre bloques de una pantalla: 24px; entre secciones de la ficha: 32px.

---

## 7. Componentes

### Navegación

- **Móvil:** barra inferior con tres pestañas, **Inicio**, **Cuaderno** y **Ajustes**, con icono + etiqueta de 12px. La activa en `--text-strong` y la inactiva en `--text-muted`. Fondo `--bg-canvas` con borde superior `--border`.
- **Escritorio:** las mismas tres en una barra superior de 56px, con el logotipo a la izquierda.

### Botones

| Tipo | Fondo | Texto | Uso |
|---|---|---|---|
| Principal | `--accent` | `#ffffff` | Una sola acción principal por pantalla: «Añadir», «Crear cuenta», «Reintentar» |
| Secundario | `--bg-raised` | `--text-strong` | «Reenviar código», «Cancelar» |
| Contorno | transparente, borde `--border-control` | `--text-strong` | Acciones terciarias |
| Peligro | transparente | `--status-error` | «Eliminar», «Eliminar cuenta» (siempre con confirmación) |

Todos: 16px de texto con peso 500, altura mínima de 44px, padding horizontal de 16px, `--radius-control`. Deshabilitado al 40% de opacidad. Mientras se envía, un *spinner* sustituye al texto y el ancho no cambia.

### Campos de texto

- Fondo `--bg-raised`, borde `--border-control`, `--radius-control`, altura de 48px y texto de 16px (con menos de 16px, Safari de iPhone hace zoom).
- Etiqueta encima (14px, `--text-muted`); error debajo (14px, `--status-error`) con icono.
- **Campo para añadir un concepto (Inicio):** 18px, botón principal «Añadir» pegado a la derecha y contador `0/200` que aparece al acercarse al límite.
- **Código de 6 dígitos:** seis casillas de 48 × 56 px, `inputmode="numeric"`, `autocomplete="one-time-code"` (iOS lo rellena desde el correo), y que permiten pegar el código entero.

### Tarjeta del Cuaderno

- `--bg-card`, `--radius-card`, borde `--border`, padding de 16px.
- Título del concepto (`body-lg`, `--text-strong`) y debajo la fecha (`caption`, `--text-muted`).
- A la derecha, la **píldora de estado** si no está completado: punto de color + texto («Generando…», «Error»), con fondo del color al 12%.
- Toda la tarjeta es pulsable. Eliminar va en un menú «⋯» o deslizando, siempre con confirmación.

### Ficha

- Contenedor `--bg-card`, `--radius-panel`, padding de 20px (móvil) o 32px (escritorio).
- Título (`heading`) con el `canonical_title` y debajo lo que escribió el usuario si es distinto (`small`, `--text-muted`).
- Tres secciones con título `heading-sm`: **Qué es**, **Para qué sirve**, **Ejemplo**. El texto va en `body` con `--text-reading`.
- `example_code`: bloque `--bg-canvas` (oscuro) o `--bg-raised` (claro), `--radius-card`, `code`, desplazamiento horizontal propio y botón «Copiar».
- Debajo, la sección **Videos**.

### Tarjetas de video

- Dos en fila en escritorio y apiladas en móvil, con 12px de separación.
- Miniatura 16:9 con `--radius-card` y `loading="lazy"`. Debajo, el título (`small`, peso 500, `--text-strong`, máximo 2 líneas) y el canal (`caption`, `--text-muted`).
- Al pasar el ratón la miniatura sube ligeramente de brillo; no hay sombra.
- Si no hay videos: texto `--text-muted` «No encontramos videos para este concepto».

### Panel de carga

- Ocupa el lugar de la ficha y tiene su misma forma: **skeleton** de un título y tres bloques de texto en `--bg-raised` con brillo animado.
- Encima, la **barra de etapas**: cuatro pasos, «En cola», «Escribiendo», «Buscando videos» y «¡Listo!». Si el trabajo vuelve a la cola tras un fallo pasajero, el texto del paso «En cola» pasa a «Reintentando…». Completado en `--status-success`, actual en `--status-progress` con pulso suave, pendiente en `--border-control`.
- Texto de la etapa actual (`body`, `--text-strong`) según la tabla de [`diseno-tecnico.md`](diseno-tecnico.md) §4.5, anunciado con `aria-live="polite"`.
- Con `prefers-reduced-motion`: sin brillo ni pulso, solo cambia el texto.
- **Error:** el panel cambia a icono + «No se pudo generar» en `--status-error` y el botón principal **Reintentar**.

### Mensajes

- **Aviso en línea:** fondo del color de estado al 12%, borde izquierdo de 3px en el color, texto `small` en `--text-strong`. Se usa para el límite diario, las notificaciones desactivadas o «revisa tu carpeta de spam».
- **Toast:** `--bg-floating`, `--radius-control`, encima de la barra inferior y 4 s de duración, para confirmaciones breves («Concepto eliminado»).

### Modal / hoja de confirmación

- En móvil es una hoja inferior y en escritorio un modal centrado de 400px. Fondo `--bg-floating`, `--radius-modal`, velo `rgba(0, 0, 0, 0.6)`.
- Para eliminar: título claro, una frase de consecuencia, botón **Peligro** y botón **Secundario** «Cancelar».

### Ajustes

- Lista de grupos en tarjetas `--bg-card`: Idioma, Tema, Recordatorios, Notificaciones, Atajo de Siri, Cuenta.
- **Días de la semana:** siete chips redondos (`--radius-full`, 40px) con la inicial. Activo: fondo `--accent` y texto blanco; inactivo: borde `--border-control`.
- **Hora:** `<input type="time">` nativo.
- **Token de Siri:** se muestra una sola vez en un bloque `code` con botón «Copiar» y el aviso de no compartir el atajo.

### Estados vacíos

- Cuaderno vacío: titular a dos tonos («Tu Cuaderno está vacío» / «Añade tu primer concepto.») y botón principal hacia Inicio.

---

## 8. Movimiento

- Transiciones de 150–200 ms, `ease-out`, solo en color, opacidad y transformaciones pequeñas.
- El brillo del skeleton dura 1,5 s por ciclo.
- Todo se desactiva con `prefers-reduced-motion: reduce`.

---

## 9. Iconos e imágenes

- Iconos de línea de 20px y trazo de 1,75, de una sola librería (p. ej. Lucide), en `--icon`.
- Las únicas imágenes son las miniaturas de YouTube. No hay ilustraciones ni fotos de stock.
- Icono de la PWA: la marca sobre `#000000`, con versiones de 192px, 512px y *maskable*.

---

## 10. Tokens CSS

```css
:root,
:root[data-theme="dark"] {
  --bg-canvas: #000000;
  --bg-card: #212121;
  --bg-raised: #292929;
  --bg-floating: #333333;

  --text-strong: #ffffff;
  --text-reading: #d4d4d4;
  --text-muted: #a3a3a3;
  --text-subtle: #8a8a8a;

  --border: rgba(229, 231, 235, 0.12);
  --border-control: #767676;
  --icon: #a3a3a3;

  --accent: #0066dd;
  --accent-hover: #0058c0;
  --brand: #0075ff;
  --accent-text: #4d9bff;
  --focus-ring: #4d9bff;

  --status-progress: #4d9bff;
  --status-success: #3ecf8e;
  --status-error: #f2555a;
  --status-warning: #f5b544;

  --shadow-float: none;
  color-scheme: dark;
}

@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) {
    --bg-canvas: #ffffff;
    --bg-card: #f5f5f5;
    --bg-raised: #ebebeb;
    --bg-floating: #ffffff;

    --text-strong: #0a0a0a;
    --text-reading: #262626;
    --text-muted: #525252;
    --text-subtle: #6b6b6b;

    --border: rgba(0, 0, 0, 0.10);
    --border-control: #7a7a7a;
    --icon: #525252;

    --accent: #0066dd;
    --accent-hover: #0058c0;
    --accent-text: #0066dd;
    --focus-ring: #0066dd;

    --status-progress: #0066dd;
    --status-success: #15803d;
    --status-error: #c62828;
    --status-warning: #a15c00;

    --shadow-float: 0 8px 24px rgba(0, 0, 0, 0.12);
    color-scheme: light;
  }
}

/* :root[data-theme="light"] repite los valores del bloque claro anterior */

:root {
  --font-sans: "Inter", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --font-mono: ui-monospace, "SF Mono", "JetBrains Mono", Consolas, monospace;

  --text-caption: 0.75rem;     /* 12px */
  --text-small: 0.875rem;      /* 14px */
  --text-body: 1rem;           /* 16px */
  --text-body-lg: 1.125rem;    /* 18px */
  --text-heading-sm: 1.25rem;  /* 20px */
  --text-heading: 1.75rem;     /* 28px */
  --text-display: 2.25rem;     /* 36px; 2.75rem desde 768px */
  --text-code: 0.875rem;       /* 14px */

  --space-1: 4px;  --space-2: 8px;   --space-3: 12px; --space-4: 16px;
  --space-5: 20px; --space-6: 24px;  --space-8: 32px; --space-10: 40px;
  --space-12: 48px; --space-16: 64px;

  --radius-control: 8px;
  --radius-card: 12px;
  --radius-panel: 16px;
  --radius-modal: 24px;
  --radius-full: 999px;

  --content-max: 720px;
  --reading-max: 68ch;
  --touch-min: 44px;
}
```
