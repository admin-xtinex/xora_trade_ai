# XORA Prediction AI

Independent AI prediction platform. This service analyzes markets, extracts features, produces predictions, validates outcomes, and measures reliability. It does **not** execute trades.

**Status:** Phase 1 architecture is complete and awaiting approval. Do not implement production code until the architecture review is signed off.

## Documents

| Deliverable | Path |
|---|---|
| Revised architecture | [docs/PHASE1_ARCHITECTURE.md](docs/PHASE1_ARCHITECTURE.md) |
| Folder structure | [docs/FOLDER_STRUCTURE.md](docs/FOLDER_STRUCTURE.md) |
| Dependency graph | [docs/DEPENDENCY_GRAPH.md](docs/DEPENDENCY_GRAPH.md) |
| Database schema | [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) |
| Docker architecture | [docs/DOCKER_ARCHITECTURE.md](docs/DOCKER_ARCHITECTURE.md) |
| Module discovery & future AI | [docs/MODULE_SYSTEM.md](docs/MODULE_SYSTEM.md) |
| Experiments & engine versions | [docs/EXPERIMENT_TRACKING.md](docs/EXPERIMENT_TRACKING.md) |
| SQL draft | [schema/001_init.sql](schema/001_init.sql) |

## Historical note

`TRADING_ENGINE_V2_DESIGN.md` is retained as a read-only reference of the previous *trading-engine* design. It is **not** the target architecture for this repository. XORA Prediction AI is a separate product boundary: prediction, validation, and qualification only.
