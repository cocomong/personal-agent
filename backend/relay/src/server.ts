import { serve } from "@hono/node-server";

import { env } from "./config";
import app from "./index";

serve({ fetch: app.fetch, port: env.PORT }, (info) => {
  console.log(`Relay listening on ${info.address}:${info.port}`);
});
