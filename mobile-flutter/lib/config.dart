/// Vapi ORG public key — designed for client-side use (ADR-5). Keep the secret
/// key server-side (n8n). Created in the dashboard: API Keys -> Public API Keys.
const String vapiPublicKey = "56802423-ec07-4bec-91f0-d8a0283959b5";

/// Vapi assistant id — "Ireh Construction PM Assistant" (backend/vapi_assistant.json).
const String vapiAssistantId = "67e2850c-1028-484d-bf52-d948826b2a7e";

/// n8n gateway base URL (device registration + briefing-time sync).
const String n8nBaseUrl = "https://n8n2.ordrnow.com";

/// n8n call-start hook: returns per-call assistant overrides
/// ({assistantId, assistantOverrides: {variableValues, firstMessage}}) so the
/// app can inject the setup-status variables and the dynamic greeting into
/// the Vapi web call (web calls don't trigger a server-side assistant-request).
const String vapiSessionHookUrl = "$n8nBaseUrl/webhook/vapi/assistant-hook";
