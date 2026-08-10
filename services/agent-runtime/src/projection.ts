const sensitive = /(?:token|secret|password|credential|authorization|cookie)/i;

function projectSchema(value: unknown, schema: any): unknown {
  if (!schema || typeof schema !== "object") return null;
  if (schema.type === "object" && value && typeof value === "object" && !Array.isArray(value)) {
    const properties = schema.properties && typeof schema.properties === "object" ? schema.properties : {};
    return Object.fromEntries(Object.entries(value as Record<string, unknown>)
      .filter(([key]) => !sensitive.test(key) && Object.hasOwn(properties, key))
      .map(([key, item]) => [key, projectSchema(item, properties[key])]));
  }
  if (schema.type === "array" && Array.isArray(value)) return value.map(item => projectSchema(item, schema.items));
  if (["string", "number", "integer", "boolean", "null"].includes(schema.type)) return value;
  return null;
}

function evidence(value: any): any {
  if (!value || typeof value !== "object") return null;
  return { kind: value.kind, reference: value.reference, digest: value.digest ?? null, summary: value.summary ?? "" };
}

export function projectCapabilityResult(result: any, maximumBytes = 16_384,
                                        agentOutputSchema?: Record<string, unknown> | null): any {
  const allowedData = projectSchema(result?.data, agentOutputSchema);
  const encoded = JSON.stringify(allowedData);
  const bytes = Buffer.from(encoded, "utf8");
  const truncated = bytes.byteLength > maximumBytes;
  const data = truncated
    ? { summary: bytes.subarray(0, maximumBytes).toString("utf8"), truncated: true }
    : allowedData;
  const error = result?.error ? {
    code: result.error.code, message: result.error.message, retryable: Boolean(result.error.retryable),
  } : null;
  return {
    ok: Boolean(result?.ok), status: result?.status, capability_id: result?.capability_id,
    major_version: result?.major_version, data,
    operation_ref: result?.operation_ref ?? null, artifact_refs: result?.artifact_refs ?? [],
    error, evidence: (result?.evidence ?? []).map(evidence).filter(Boolean),
    warnings: (result?.warnings ?? []).map((item: unknown) => String(item).slice(0, 1000)),
    correlation: { request_id: result?.correlation?.request_id, trace_id: result?.correlation?.trace_id },
    truncated,
  };
}
