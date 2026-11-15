# Backup — ASTRA visual styling before the colour redesign (2026-11-15)

Original "hull-blue / deep space" dark-only styling, copied unchanged before the light-blue / white / charcoal /
purple redesign with light and dark themes. Do not edit or overwrite these files.

* `frontend/src/styles.css` — the complete original design system (CSS variables in `:root`, all component styles)
* `frontend/index.html` — original document head (theme-color, colour-scheme)
* `frontend/src/components/Charts.tsx`, `ui.tsx`, `BodyMap.tsx`, `frontend/src/pages/Environment.tsx` — components
  that contained hard-coded colours (chart palette, avatar hues, location colours)
* `frontend/public/` — PWA manifest, icon, service worker as they were
* `frontend/dist-assets/` — the compiled stylesheet of the previous production build

To restore the old look: copy these files back to their original paths and run `npm run build` in `frontend/`.
