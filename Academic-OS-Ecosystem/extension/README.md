# Chrome extension

This folder holds the extension's source files. It is not loadable as-is.

- `manifest.template.json`: the manifest with the API host left as a placeholder.
- `background.js`: toolbar button handler.
- `icons/`: extension icons.

The loadable extension is generated into `extension/dist/` (which contains
`manifest.json`, the built pages, and the vendored libraries). Build it with:

```bash
python scripts/build_extension.py --api-url https://<backend> --google-client-id <id>.apps.googleusercontent.com
```

Then, in Chrome: `chrome://extensions` → Developer mode → **Load unpacked** →
select `extension/dist`. Do not select this `extension/` folder.

`dist/` is git-ignored, so a fresh clone must run the build first.
See `docs/CHROME_EXTENSION.md` for the full setup.
