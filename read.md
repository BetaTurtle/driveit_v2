curl -fsSL https://deno.land/install.sh | sh
deno install -gArf jsr:@deno/deployctl

https://dash.deno.com/projects/driveit-v

deployctl deploy --project=driveit-v --entrypoint server.ts

deno run --allow-net ./server.ts