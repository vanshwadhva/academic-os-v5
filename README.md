# Academic OS

The workspace is split into two deployable parts:

- [`Academic-OS-Chrome-Etension/`](Academic-OS-Chrome-Etension/) — Manifest V3 browser extension source. Its `manifest.json` is at the folder root, so this folder can be loaded unpacked in Chrome or packaged for extension distribution.
- [`Academic-OS-Ecosystem/`](Academic-OS-Ecosystem/) — the student tracker web app, FastAPI backend, Lumen integration, ML components, and deployment files.

GitHub Actions workflows can be added under `.github/workflows/` at the repository root. The main Git repository remains at the workspace root; publish both folders together, or use the extension folder as the source directory when packaging the Chrome extension.

See each folder's README for setup and deployment instructions.
