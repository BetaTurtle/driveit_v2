# DriveIt Bot v2

## Deno Backend Deployment

```bash
curl -fsSL https://deno.land/install.sh | sh
deno install -gArf jsr:@deno/deployctl

https://dash.deno.com/projects/driveit-v

deployctl deploy --project=driveit-v --entrypoint server.ts

deno run --allow-net ./server.ts
```

## Frontend

The frontend is located in the `frontend` directory and is built using Vite.

```bash
cd frontend
npm install
npm run build
```

The production assets are built to the `docs/` directory for GitHub Pages.
