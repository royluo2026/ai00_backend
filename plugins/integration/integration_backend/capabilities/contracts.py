from __future__ import annotations


def obj(properties: dict, required: tuple[str, ...] = ()) -> dict:
    value = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        value["required"] = list(required)
    return value


STRING = {"type": "string", "minLength": 1}
INTEGER = {"type": "integer"}
POSITIVE = {"type": "integer", "minimum": 1}
FIELD = obj({"source_field": STRING, "target_field": STRING, "transform_expression": STRING}, ("source_field", "target_field"))
REF = obj({"gid": STRING, "revision": POSITIVE, "status": STRING}, ("gid", "revision", "status"))
SEARCH = obj({"query": STRING, "limit": {"type": "integer", "minimum": 1, "maximum": 200}})
MAPPING_INPUT = {
    "datasource_gid": STRING, "name": STRING, "source_object": STRING,
    "target_domain": STRING, "target_capability_id": STRING, "target_major_version": POSITIVE,
    "minimum_catalog_release": STRING, "field_mappings": {"type": "array", "items": FIELD},
}


INPUT_SCHEMAS = {
    "integration.connector.create": obj({"name": STRING, "connector_type": STRING, "host": STRING, "port": {"type": "integer", "minimum": 1, "maximum": 65535}, "database_name": STRING, "username": STRING, "credential_ref": STRING}, ("name", "connector_type", "host", "port", "database_name", "username", "credential_ref")),
    "integration.connector.update": obj({"gid": STRING, "expected_revision": POSITIVE, "name": STRING, "credential_ref": STRING}, ("gid", "expected_revision")),
    "integration.connector.archive": obj({"gid": STRING, "expected_revision": POSITIVE}, ("gid", "expected_revision")),
    "integration.connector.search": SEARCH,
    "integration.connector.connection.test": obj({"gid": STRING}, ("gid",)),
    "integration.connector.schema.discover": obj({"gid": STRING}, ("gid",)),
    "integration.mapping.create": obj(MAPPING_INPUT, ("datasource_gid", "name", "source_object", "target_domain", "target_capability_id", "target_major_version", "minimum_catalog_release")),
    "integration.mapping.update": obj({"gid": STRING, "expected_revision": POSITIVE, "field_mappings": {"type": "array", "items": FIELD}}, ("gid", "expected_revision")),
    "integration.mapping.archive": obj({"gid": STRING, "expected_revision": POSITIVE}, ("gid", "expected_revision")),
    "integration.mapping.get": obj({"gid": STRING}, ("gid",)),
    "integration.mapping.search": SEARCH,
    "integration.mapping.preview": obj({"gid": STRING, "limit": {"type": "integer", "minimum": 1, "maximum": 200}}, ("gid",)),
    "integration.sync.start": obj({"mapping_gid": STRING}, ("mapping_gid",)),
}


OUTPUT_SCHEMAS = {
    "integration.connector.create": REF,
    "integration.connector.update": obj({"gid": STRING, "revision": POSITIVE, "changed": {"type": "boolean"}}, ("gid", "revision", "changed")),
    "integration.connector.archive": obj({"gid": STRING, "archived": {"type": "boolean"}}, ("gid", "archived")),
    "integration.connector.search": obj({"items": {"type": "array", "items": {"type": "object", "additionalProperties": True}}}, ("items",)),
    "integration.connector.connection.test": obj({"reachable": {"type": "boolean"}, "latency_ms": INTEGER}, ("reachable",)),
    "integration.connector.schema.discover": obj({"objects": {"type": "array", "items": {"type": "object", "additionalProperties": True}}}, ("objects",)),
    "integration.mapping.create": REF,
    "integration.mapping.update": obj({"gid": STRING, "revision": POSITIVE, "changed": {"type": "boolean"}}, ("gid", "revision", "changed")),
    "integration.mapping.archive": obj({"gid": STRING, "archived": {"type": "boolean"}}, ("gid", "archived")),
    "integration.mapping.get": obj({"gid": STRING, "revision": POSITIVE, "target_capability_id": STRING, "field_mappings": {"type": "array", "items": FIELD}}, ("gid", "revision", "target_capability_id", "field_mappings")),
    "integration.mapping.search": obj({"items": {"type": "array", "items": {"type": "object", "additionalProperties": True}}}, ("items",)),
    "integration.mapping.preview": obj({"rows": {"type": "array", "items": {"type": "object", "additionalProperties": True}}, "truncated": {"type": "boolean"}}, ("rows", "truncated")),
    "integration.sync.start": obj({"run_id": STRING, "operation_ref": obj({"operation_id": STRING, "status": {"type": "string", "enum": ["accepted"]}, "version": POSITIVE}, ("operation_id", "status", "version"))}, ("run_id", "operation_ref")),
}

__all__ = ["INPUT_SCHEMAS", "OUTPUT_SCHEMAS"]
