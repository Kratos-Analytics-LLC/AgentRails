# Plan Maestro: AgentRails como capa de seguridad para agentes

## El reenfoque

AgentRails nació resolviendo un problema de trading, pero el trading es solo el
**dominio donde apareció el problema**, no el problema. Lo valioso y reutilizable
es el patrón:

> **política declarativa → validar la acción propuesta → dry-run → registro
> auditable → circuit breaker tras fallos.**

Ese patrón no tiene nada específico de finanzas. Aplica a **cualquier acción
consecuente que tome un agente autónomo**: mandar correos, hacer compras, ejecutar
código o comandos, gastar presupuesto de API, modificar infraestructura, publicar
contenido, escribir en una base de datos. Hoy más gente cablea agentes (Claude y
otros) directamente a herramientas que ejecutan acciones irreversibles, y casi
nadie pone una capa entre "el agente decidió" y "la acción ocurrió".

**Ese hueco es AgentRails.** El objetivo del proyecto deja de ser "otro bot de
trading" (eso ya existe en otro lado) y pasa a ser **la capa de seguridad y
gobernanza que cualquier agente enchufa antes de actuar** — con el trading como
el primer adaptador de referencia, no como el producto.

---

## El núcleo genérico

Las tres piezas actuales ya son, en el fondo, genéricas; solo tienen nombres de
trading. La generalización es sobre todo de nombres y de un adaptador:

| Hoy (específico de trading) | Núcleo genérico |
|---|---|
| `PlannedOrder` (symbol, side, dollar_amount) | `Action` (tipo, objetivo, magnitud/coste, reversible?) |
| `TradePlan` (lista de órdenes) | `ActionPlan` (lote de acciones propuestas) |
| `GuardrailConfig` (allowed_symbols, max_order_usd…) | `Policy` (reglas declarativas) |
| `validate_plan()` | mismo motor puro: allow / deny / needs-approval + feedback |
| `Ledger`, `CircuitBreaker` | ya son agnósticos — casi no cambian |

Los guardrails actuales se traducen 1:1 a primitivas de dominio general, y esa es
la prueba de que la idea generaliza:

- lista blanca de símbolos → **lista blanca de objetivos** (destinatarios, dominios, comandos, recursos)
- `max_order_usd` → **máximo por acción** (coste, tamaño, alcance)
- `weekly_cap_usd` → **presupuesto por ventana** (gasto diario, llamadas/hora, correos/día)
- `max_orders_per_run` → **máximo de acciones por ejecución**
- ventas on/off, "no vender lo que no tienes" → **acciones irreversibles/destructivas requieren confirmación**
- `max_position_concentration` → **límite de exposición** (no más de X% a un proveedor/recurso/destinatario)
- `human_approval_threshold_usd` → **umbral de aprobación humana** sobre cualquier eje de "coste"
- `shadow_mode`, `to_feedback_prompt()`, circuit breaker → idénticos, ya son de propósito general

---

## Fase 0 — Endurecer lo que ya hay (antes de generalizar)

No se generaliza sobre cimientos flojos.

- **Tests** de los guardrails nuevos (shadow mode, stop-loss, concentración,
  umbral de aprobación): sin cubrir. Prioridad #1.
- **Cablear Ledger y CircuitBreaker** dentro de `mcp_server.py` (hoy solo llama a
  `validate_plan`; no audita ni respeta el breaker).
- **Manejo de secretos** documentado: credenciales en entorno / `.env` (ya
  ignorado), nunca en el repo.

Salida: núcleo probado y auditado, con el gateway MCP integrando las tres piezas.

---

## Fase 1 — Extraer el núcleo genérico

Refactor sin romper el ejemplo de trading (compatibilidad hacia atrás).

- **Paso 1:** definir `Action`, `ActionPlan` y `Policy` agnósticos, y un motor
  `validate(plan, policy, context)` con las primitivas de la tabla de arriba.
- **Paso 2:** reescribir el trading como **adaptador de referencia** encima del
  núcleo: `Order` es un `Action`, `GuardrailConfig` es una `Policy` de trading.
  El API actual de trading sigue funcionando igual.
- **Paso 3:** el Ledger y el CircuitBreaker apenas cambian (ya son genéricos);
  ajustar nombres de campos para que no asuman "símbolo/lado".

Salida: `agentrails.core` (genérico) + `agentrails.adapters.trading` (ejemplo).

---

## Fase 2 — Un segundo adaptador que pruebe la generalidad

La mejor prueba de que el núcleo es genérico es un segundo dominio **no
financiero**. Candidatos por dificultad creciente:

- **Gasto de API / presupuesto** (fácil, muy demandado): límite por llamada,
  presupuesto diario, corte tras N fallos. Ideal para agentes que consumen LLMs.
- **Envío de correos/mensajes** (medio): lista blanca de destinatarios, tope
  diario, aprobación humana por encima de X destinatarios, dry-run que muestra qué
  se enviaría.
- **Ejecución de comandos/código** (alto valor, alto riesgo): lista blanca de
  comandos, bloqueo de operaciones destructivas sin confirmación, registro
  auditable de todo lo ejecutado.

Elegir **uno** y construirlo entero (modelo + política + validación + ejemplo +
tests). Con dos adaptadores funcionando, el mensaje del proyecto es demostrable,
no teórico.

---

## Fase 3 — Documentación y posicionamiento como herramienta de dev

Siendo público y MIT, el valor crece si otros lo adoptan.

- README reorientado: "capa de seguridad para agentes de IA", con trading y el
  segundo adaptador como ejemplos.
- Guía de "escribe tu propio adaptador" (el patrón en ~30 líneas).
- Ejemplos de integración con MCP / Claude Desktop / frameworks de agentes.

---

## Lo que este proyecto NO es

- **No es un bot de trading.** Esa parte ya está resuelta en otro lado; aquí el
  trading es solo el ejemplo de referencia.
- **No decide qué hacer.** Decide qué está *permitido* hacer y lo deja registrado.
- **No es un servicio alojado ni guarda credenciales.** Nada habla con la red por
  su cuenta; las claves y las cuentas son del usuario, en su máquina.

---

## Siguiente acción inmediata

Cerrar la **Fase 0** (tests + cablear ledger/breaker en el gateway) y, en paralelo,
decidir el **segundo adaptador** de la Fase 2 — porque esa elección es la que
convierte "librería de trading con ínfulas" en "capa de seguridad para agentes".

> Herramienta para automatizar acciones propias con credenciales propias. No es
> consejo de inversión ni de ningún tipo. AgentRails hace cumplir los límites que
> tú configuras; no elimina el riesgo de la acción subyacente.
