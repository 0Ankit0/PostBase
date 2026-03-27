# PostBase

PostBase is a backend platform with a control plane for projects, environments, provider bindings, and capability operations across auth, data, storage, functions, and events.

## Quick Start

1. Read the docs index: [`docs/README.md`](docs/README.md).
2. Review the canonical system design: [`docs/system-design/README.md`](docs/system-design/README.md).
3. Set up local project files: `make setup`.
4. Start dependencies: `make infra-up`.
5. Run backend migrations: `make backend-migrate`.
6. Start services as needed:
   - Backend: `make backend-dev`
   - Frontend: `make frontend-dev`
   - Mobile: `make mobile-dev`

## Documentation

- Canonical architecture and product specification: [`docs/system-design`](docs/system-design).
- Requirement/API parity tracker: [`docs/system-design/parity-matrix.md`](docs/system-design/parity-matrix.md).
- Documentation validation: `make docs`.

## Validation and Testing

- Docs: `make docs`
- Backend lint/tests: `make backend-lint` / `make backend-test`
- Frontend lint/tests: `make frontend-lint` / `make frontend-test`
- Mobile lint/tests: `make mobile-lint` / `make mobile-test`
- Full local quality bar: `make ci`
