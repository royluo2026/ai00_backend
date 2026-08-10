export interface RuntimeConfig {
  port: number;
  backendUrl: string;
  modelProvider: string;
  modelId: string;
  databaseUrl: string;
  sessionEncryptionKey: Buffer;
  serviceCredential: string;
}

function required(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

export function loadConfig(): RuntimeConfig {
  const key = Buffer.from(required("SESSION_ENCRYPTION_KEY"), "base64");
  if (key.byteLength !== 32) {
    throw new Error("SESSION_ENCRYPTION_KEY must be a base64-encoded 32-byte key");
  }
  const serviceCredential = required("AGENT_RUNTIME_SERVICE_TOKEN");
  if (serviceCredential.length < 32) throw new Error("AGENT_RUNTIME_SERVICE_TOKEN must contain at least 32 characters");
  return {
    port: Number(process.env.PORT || "8090"),
    backendUrl: (process.env.AI00_BACKEND_URL || "http://127.0.0.1:8080").replace(/\/$/, ""),
    modelProvider: process.env.PI_MODEL_PROVIDER || "openai",
    modelId: process.env.PI_MODEL_ID || "gpt-5-mini",
    databaseUrl: required("AI00_AGENT_DB_URL"),
    sessionEncryptionKey: key,
    serviceCredential,
  };
}
