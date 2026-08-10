const sensitive = /(?:token|secret|password|credential|authorization|cookie)/i;
function project(value: unknown, schema: any): unknown {
  if (!schema || typeof schema !== "object") return null;
  if ((schema.type === "object" || schema.properties) && value && typeof value === "object" && !Array.isArray(value)) {
    const properties = schema.properties || {};
    return Object.fromEntries(Object.entries(value as Record<string, unknown>)
      .filter(([key]) => !sensitive.test(key) && Object.hasOwn(properties, key))
      .map(([key, item]) => [key, project(item, properties[key])]));
  }
  if (schema.type === "array" && Array.isArray(value)) return value.map(item => project(item, schema.items));
  if (["string", "number", "integer", "boolean", "null"].includes(schema.type)) return value;
  return null;
}
export function projectResult(result: any, schema?: Record<string, unknown> | null,
                              maximumBytes = 16_384): Record<string, unknown> {
  const allowed = project(result?.data, schema);
  const encoded = Buffer.from(JSON.stringify(allowed), "utf8");
  const truncated = encoded.byteLength > maximumBytes;
  return {
    ok: Boolean(result?.ok), status: result?.status, capability_id: result?.capability_id,
    major_version: result?.major_version,
    data: truncated ? { summary: encoded.subarray(0, maximumBytes).toString("utf8"), truncated: true } : allowed,
    operation_ref: result?.operation_ref ?? null, artifact_refs: result?.artifact_refs ?? [],
    error: result?.error ? { code: result.error.code, message: result.error.message, retryable: Boolean(result.error.retryable) } : null,
    evidence: (result?.evidence ?? []).map((item: any) => ({ kind: item.kind, reference: item.reference, digest: item.digest ?? null, summary: item.summary ?? "" })),
    warnings: (result?.warnings ?? []).map((item: unknown) => String(item).slice(0, 1000)),
    correlation: { request_id: result?.correlation?.request_id, trace_id: result?.correlation?.trace_id }, truncated,
  };
}
