import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";

export function seal(value: unknown, key: Buffer): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const plaintext = Buffer.from(JSON.stringify(value), "utf8");
  const ciphertext = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  return ["v1", iv.toString("base64url"), cipher.getAuthTag().toString("base64url"), ciphertext.toString("base64url")].join(".");
}

export function open<T>(encoded: string, key: Buffer): T {
  const [version, ivPart, tagPart, dataPart] = encoded.split(".");
  if (version !== "v1" || !ivPart || !tagPart || !dataPart) throw new Error("Unsupported session ciphertext");
  const decipher = createDecipheriv("aes-256-gcm", key, Buffer.from(ivPart, "base64url"));
  decipher.setAuthTag(Buffer.from(tagPart, "base64url"));
  const plaintext = Buffer.concat([decipher.update(Buffer.from(dataPart, "base64url")), decipher.final()]);
  return JSON.parse(plaintext.toString("utf8")) as T;
}
