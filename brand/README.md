# Brand assets

Source files (artwork as designed, metadata stripped):

- `logo.svg` — "bu" + wave mark on a black square, 2000×2000.
- `logo-transparent.svg` — same artwork, no background.

Derived (crop the `viewBox` only — never edit the artwork there):

| File | From | `viewBox` | Used for |
|---|---|---|---|
| `frontend/public/favicon.svg` | `logo.svg` | `557 574 880 880` | browser tab icon |
| `desktop/src-tauri/app-icon.svg` | `logo.svg` | `557 574 880 880` | app/installer/tray icons — regenerate with `cd desktop && npx tauri icon src-tauri/app-icon.svg` (delete the `android/` and `ios/` output) |
| `frontend/public/logo-mark.svg` | `logo-transparent.svg` | `642 768 710 492` | `<Logo />` in the UI, website, legal pages |

The mark itself spans x 662–1332, y 788–1240 of the 2000-unit canvas; the
crops above are padded around that. The full-canvas originals leave the mark
tiny at icon sizes, which is why the icons use the crop.
