# Architecture Overview

The Aegis Agent Platform is designed around four specialist agents:

- Alina: strategic coordination
- Kian: operational execution
- Bita: analysis and synthesis
- Aylin: quality and validation

## Core principles

1. A strict four-agent runtime model.
2. Shared contracts in `core/`.
3. A central orchestration layer in `app/`.
4. English-only project artifacts.

## Runtime flow

1. The application entry point invokes the orchestrator.
2. The orchestrator reads the agent registry.
3. Agent metadata is exposed through shared contracts.
4. Each specialist handles a task in its defined role.

## Phase coverage

- Phase 0: project constitution and constraints
- Phase 1: architecture scaffold and registry foundation
