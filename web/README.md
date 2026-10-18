# FinePrint web

Next.js (App Router, TypeScript) front end for FinePrint.

## Run

```bash
cp .env.example .env.local      # set NEXT_PUBLIC_API_BASE if the API is not on localhost:8000
npm install
npm run dev -- -p 3001          # development
npm run build && npm run start -- -p 3001   # production
```

`NEXT_PUBLIC_API_BASE` and `NEXT_PUBLIC_REPO_URL` (used for the agent tools link, default https://github.com/kinnuworks/fineprint) are read at build time. On Vercel, set it in the project's environment variables before deploying.

## Routes

- `/` landing: Hub-wide numbers from `/api/stats` (`graph_audit`, `hub_api_comparison`), search with suggestions from `/api/search`, hero models, URL-swap hint, and findings from `/api/load-bearing` and `/api/relicense-points`.
- `/{org}/{name}` and `/{name}`: the report, with the decision (ALLOW, CONDITIONS, BLOCK) for commercial or non-commercial use (`?use=noncommercial`) next to the title verdict. This is the URL swap, so `huggingface.co/meta-llama/Llama-3.1-8B` becomes `<this site>/meta-llama/Llama-3.1-8B`. Trailing Hub paths such as `/tree/main` are ignored. `?graph=false` opens the "Direct parents only" view, which reads one hop up as the model page does.

The report page also has a "Read the card" button (`POST /api/read-card/...`, about 10 s on a first read) that lists each lineage claim found in the model card with its quoted sentence and status, shows the verdict before and after, and replaces the report with the one the response returns. Under LIENS and CLOUDED verdicts it lists clean alternatives from `/api/substitutes/...`.

The report is rendered on the server from `/api/report/...` and hydrated on the client. The graph toggle and the downstream panel (`/api/descendants/...`) fetch from the browser.

## Fallbacks

`public/fallback/` holds saved API responses: `/api/stats`, `/api/load-bearing`, `/api/relicense-points`, and for each hero model the report in both lineage modes and both uses, descendants, substitutes, and the card read for the LeoScorpius model. `bundle.json` collects them all and is what the site imports; the per-file copies are there to inspect. When the API cannot be reached, the landing page and the hero reports use these copies and say so on the page. Other models show an "API not reachable" message with links to the saved reports.

Refresh them with the API running:

```bash
NEXT_PUBLIC_API_BASE=http://localhost:8000 node scripts/refresh-fallback.mjs
```

The hero list lives in `scripts/refresh-fallback.mjs` and `app/page.tsx`.

## Graph

The chain of title is drawn with `@falkordb/canvas` (tree layout, custom node drawing so labels sit under the nodes). Edges come from each lien's proof paths, labelled with the relation. Ancestors that no proof path passes through are linked to the model with a dashed edge, since the API returns their depth but not their parent.

## Design

The site follows the indie app design system: cream mood (`data-mood="cream"`), terracotta accent (`data-accent="terracotta"`), Plus Jakarta Sans with Geist Mono and one Instrument Serif italic phrase, always light. `app/globals.css` starts with the system's foundation CSS pasted verbatim, then adds FinePrint's styles. Verdict and decision colours (`--v-allow`, `--v-cond`, `--v-block`, `--v-unknown`) and license colours (`--lic-*`) are product colours used only inside report UI and mockups. The app icon is `components/AppIcon.tsx` (also `app/icon.svg`).

Screenshots at 1440px and 375px are in `screenshots/`.
