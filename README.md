Pega estas líneas en el README de AgentRails, justo debajo de la línea `# AgentRails`:

[![CI](https://github.com/Kratos-Analytics-LLC/AgentRails/actions/workflows/ci.yml/badge.svg)](https://github.com/Kratos-Analytics-LLC/AgentRails/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/kratos-agentrails)](https://pypi.org/project/kratos-agentrails/)
[![Python](https://img.shields.io/pypi/pyversions/kratos-agentrails)](https://pypi.org/project/kratos-agentrails/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

Texto sugerido para el Release v0.1.0 (Releases → Draft a new release → tag v0.1.0):

Título: AgentRails v0.1.0

Primera versión pública. Capa de seguridad para agentes de IA que ejecutan acciones reales:
política declarativa (JSON/YAML), validación fail-closed, dry-run, ledger de auditoría en CSV,
circuit breaker persistente, decorador `@guarded`, CLI `agentrails report`, gateway MCP de
referencia y tres adaptadores (trading, api_spend, shell). 133 tests, CI en Python 3.10–3.13.
Instalación: `pip install kratos-agentrails`.
