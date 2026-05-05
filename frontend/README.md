# Restriction Limits — Frontend (suggested layout)

Empty by design: this folder is the agreed home for a Vite + React +
TypeScript app. A developer with Node available scaffolds it once with:

```bash
npm create vite@latest . -- --template react-ts
npm install
npm install @tanstack/react-query recharts
```

## Suggested structure

```
frontend/
  src/
    api/
      client.ts          # fetch wrapper around the backend
      types.ts           # mirrors backend/models.py
    components/
      BreachTable.tsx
      AxisCards.tsx
      UtilizationChart.tsx
      DateSwitcher.tsx
    pages/
      Dashboard.tsx
      Detail.tsx          # bucket detail with timeseries
    App.tsx
    main.tsx
  index.html
  vite.config.ts
  package.json
```

## Endpoint cheat-sheet (consumed by `src/api/client.ts`)

| Endpoint | Returns |
| --- | --- |
| `GET /api/health` | service status |
| `GET /api/limits/dates` | list of `{date, file}` |
| `GET /api/report?date=YYYY-MM-DD&breached_only=true` | `BreachReport` |
| `GET /api/report?severity=red&severity=amber` | filtered `BreachReport` |
| `GET /api/report/summary` | cards (per-axis severity counts) |
| `GET /api/report/timeseries?axis=País&key={"País":"Portugal"}` | per-day utilisation |

## Severity colour key (matches the backend)

| Severity | Meaning | Suggested CSS |
| --- | --- | --- |
| `green` | utilisation ≤ 80 % | `#16a34a` |
| `amber` | 80 % < utilisation ≤ 100 % | `#f59e0b` |
| `red`   | utilisation > 100 % (breach) | `#dc2626` |
| `none`  | no cap defined for the bucket | `#9ca3af` |

## Build for the desktop bundle

```bash
npm run build      # outputs frontend/dist/
```

The PyInstaller spec at `packaging/RestrictionLimits.spec` picks up
`frontend/dist/` automatically when present.
