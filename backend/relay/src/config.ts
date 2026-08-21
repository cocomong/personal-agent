import { z } from "zod";

/**
 * Env config parsed at process boundary (the untrusted input of a server).
 * All values are required; a missing one fails loud at startup, not mid-request.
 */
const envSchema = z.object({
  ELEVENLABS_AGENT_ID: z.string().min(1),
  ELEVENLABS_API_KEY: z.string().min(1),
  RELAY_AUTH_TOKEN: z.string().min(1),
  PORT: z.coerce.number().int().positive().default(3001),
});

const parsed = envSchema.safeParse(process.env);
if (!parsed.success) {
  throw new Error(`Invalid environment: ${parsed.error.message}`);
}

export const env = parsed.data;
