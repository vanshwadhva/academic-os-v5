# Academic OS Chrome Extension

This folder is the complete Manifest V3 extension source. Keep `manifest.json` at this folder's root when loading or packaging the extension.

## Load locally

1. Open `chrome://extensions` and enable **Developer mode**.
2. Select **Load unpacked** and choose this `Academic-OS-Chrome-Etension` folder.

## Publish from GitHub

Publish the workspace repository to GitHub. The extension source is under this folder, with its entry point, icons, content scripts, service worker, popup, and dashboard kept together. For Chrome Web Store packaging, create a ZIP whose top level contains this folder's `manifest.json` and extension source directories. The local `archive/` folder is retained for reference and excluded from the publishable source.

## Contents

- `manifest.json` and `config.js`: extension metadata and runtime configuration.
- `background/`, `content_scripts/`, and `network/`: service worker, page bridge, and Lumen data capture.
- `api/`, `authentication/`, `storage/`, and `sync/`: authentication, persistence, and sync queue.
- `popup/`, `dashboard/`, and `icons/`: extension UI and icons.
- `docs/`: integration notes and the extension audit report.

The companion student tracker and backend are in [`../Academic-OS-Ecosystem/`](../Academic-OS-Ecosystem/).
