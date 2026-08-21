import WebSocket from "ws";

import { env } from "./config";

/**
 * A single WebSocket conversation with the ElevenLabs agent. Speaks the
 * conversational protocol directly: sends `user_message` frames and resolves
 * on the next `agent_response` frame. One session = one conversation.
 */
export class AgentSession {
  readonly sessionId: string;
  private readonly socket: WebSocket;
  private readonly pending = new Set<(reply: string) => void>();
  private closed = false;

  constructor(sessionId: string, socket: WebSocket) {
    this.sessionId = sessionId;
    this.socket = socket;

    this.socket.on("message", (raw) => {
      this.handleMessage(raw.toString());
    });

    this.socket.on("close", () => {
      this.closed = true;
      this.pending.forEach((resolve) => resolve(""));
      this.pending.clear();
    });
  }

  private handleMessage(raw: string): void {
    let event: Record<string, unknown>;
    try {
      event = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return;
    }

    if (event.type === "agent_response") {
      const payload = event.agent_response_event;
      const reply =
        typeof payload === "object" && payload !== null && "agent_response" in payload
          ? String(payload.agent_response).trim()
          : "";
      const resolve = this.pending.values().next().value;
      if (resolve) {
        this.pending.delete(resolve);
        resolve(reply);
      }
    }
  }

  /** Sends one user text turn and resolves with the agent's text reply. */
  sendUserMessage(text: string): Promise<string> {
    if (this.closed) {
      return Promise.reject(new Error("Session closed"));
    }
    return new Promise((resolve) => {
      this.pending.add(resolve);
      this.socket.send(JSON.stringify({ type: "user_message", text }));
    });
  }

  close(): void {
    this.closed = true;
    this.socket.close();
  }
}

function socketFor(agentId: string, apiKey: string): WebSocket {
  return new WebSocket(
    `wss://api.elevenlabs.io/v1/convai/conversation?agent_id=${agentId}`,
    { headers: { "xi-api-key": apiKey } },
  );
}

/**
 * Maintains a single shared agent session for the relay process. For a
 * multi-tenant deployment this becomes a session pool keyed by caller id.
 */
export async function openAgentSession(): Promise<AgentSession> {
  const socket = socketFor(env.ELEVENLABS_AGENT_ID, env.ELEVENLABS_API_KEY);
  await new Promise<void>((resolve, reject) => {
    socket.once("open", resolve);
    socket.once("error", (err) => reject(err));
  });
  return new AgentSession(`session-${Date.now()}`, socket);
}
