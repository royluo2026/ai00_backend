import * as z from "zod/v4";

export function jsonSchemaToZod(schema: Record<string, any>): z.ZodType {
  if (Array.isArray(schema.enum) && schema.enum.length > 0) {
    const literals = schema.enum.map((value: any) => z.literal(value));
    return literals.length === 1 ? literals[0]! : z.union(literals as any);
  }
  switch (schema.type) {
    case "string": {
      let value = z.string();
      if (typeof schema.minLength === "number") value = value.min(schema.minLength);
      if (typeof schema.maxLength === "number") value = value.max(schema.maxLength);
      if (typeof schema.pattern === "string") value = value.regex(new RegExp(schema.pattern));
      return schema.description ? value.describe(schema.description) : value;
    }
    case "integer": {
      let value = z.number().int();
      if (typeof schema.minimum === "number") value = value.min(schema.minimum);
      if (typeof schema.maximum === "number") value = value.max(schema.maximum);
      if (typeof schema.exclusiveMinimum === "number") value = value.gt(schema.exclusiveMinimum);
      if (typeof schema.exclusiveMaximum === "number") value = value.lt(schema.exclusiveMaximum);
      return value;
    }
    case "number": {
      let value = z.number();
      if (typeof schema.minimum === "number") value = value.min(schema.minimum);
      if (typeof schema.maximum === "number") value = value.max(schema.maximum);
      if (typeof schema.exclusiveMinimum === "number") value = value.gt(schema.exclusiveMinimum);
      if (typeof schema.exclusiveMaximum === "number") value = value.lt(schema.exclusiveMaximum);
      return value;
    }
    case "boolean": return z.boolean();
    case "array": {
      let value = z.array(jsonSchemaToZod(schema.items || {}));
      if (typeof schema.minItems === "number") value = value.min(schema.minItems);
      if (typeof schema.maxItems === "number") value = value.max(schema.maxItems);
      return value;
    }
    case "object": {
      const required = new Set<string>(schema.required || []);
      const shape: Record<string, z.ZodType> = {};
      for (const [name, child] of Object.entries<Record<string, any>>(schema.properties || {})) {
        const value = jsonSchemaToZod(child);
        shape[name] = required.has(name) ? value : value.optional();
      }
      let value = z.object(shape);
      value = schema.additionalProperties === false ? value.strict() : value.loose();
      if (typeof schema.minProperties === "number") value = value.refine((item) => Object.keys(item).length >= schema.minProperties);
      if (typeof schema.maxProperties === "number") value = value.refine((item) => Object.keys(item).length <= schema.maxProperties);
      return value;
    }
    default: return z.unknown();
  }
}