import { Hono } from "hono";
import { z } from "zod";

import { openAgentSession } from "./AgentSession";
import { env } from "./config";

const messageSchema = z.object({
  message: z.string().min(1).max(4000),
});

const app = new Hono();

let currentSession: Awaited<ReturnType<typeof openAgentSession>> | null = null;

async function session(): Promise<Awaited<ReturnType<typeof openAgentSession>>> {
  if (currentSession) return currentSession;
  currentSession = await openAgentSession();
  return currentSession;
}

function authorized(authHeader: string | undefined): boolean {
  return authHeader === `Bearer ${env.RELAY_AUTH_TOKEN}`;
}

app.post("/api/agent/text", async (c) => {
  const auth = c.req.header("authorization");
  if (!authorized(auth)) {
    return c.json({ error: "Unauthorized" }, 401);
  }

  const parsed = messageSchema.safeParse(await c.req.json());
  if (!parsed.success) {
    return c.json({ error: "Invalid message body" }, 400);
  }

  const s = await session();
  const reply = await s.sendUserMessage(parsed.data.message);
  return c.json({ reply });
});

export default app;
