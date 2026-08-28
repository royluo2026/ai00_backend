from __future__ import annotations


def obj(properties: dict, required: tuple[str, ...] = (), **keywords) -> dict:
    value = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
        **keywords,
    }
    if required:
        value["required"] = list(required)
    return value


STRING = {"type": "string", "minLength": 1}
INTEGER = {"type": "integer"}
POSITIVE = {"type": "integer", "minimum": 1}
LIMIT = {"type": "integer", "minimum": 1, "maximum": 200}
IDEMPOTENCY = {"type": "string", "minLength": 1, "maxLength": 255}

FIELD = obj(
    {"source_field": STRING, "target_field": STRING, "transform_expression": STRING},
    ("source_field", "target_field"),
)
FIELD_RESULT = obj(
    {"gid": STRING, "revision": POSITIVE, **FIELD["properties"]},
    ("gid", "revision", "source_field", "target_field"),
)
OPERATION_REF = obj(
    {
        "operation_id": STRING,
        "status": {"type": "string", "enum": ["accepted", "succeeded", "failed", "outcome_unknown"]},
        "version": POSITIVE,
    },
    ("operation_id", "status", "version"),
)
CONNECTOR = obj(
    {
        "gid": STRING, "revision": POSITIVE, "name": STRING, "connector_type": STRING,
        "host": STRING, "port": {"type": "integer", "minimum": 1, "maximum": 65535},
        "database_name": STRING, "username": STRING, "status": STRING,
    },
    ("gid", "revision", "name", "connector_type", "host", "port", "database_name", "username", "status"),
)
MAPPING = obj(
    {
        "gid": STRING, "revision": POSITIVE, "datasource_gid": STRING, "name": STRING,
        "source_object": STRING, "target_domain": STRING, "target_capability_id": STRING,
        "target_major_version": POSITIVE, "minimum_catalog_release": STRING, "status": STRING,
    },
    (
        "gid", "revision", "datasource_gid", "name", "source_object", "target_domain",
        "target_capability_id", "target_major_version", "minimum_catalog_release", "status",
    ),
)
MAPPING_DETAIL = obj(
    {**MAPPING["properties"], "field_mappings": {"type": "array", "items": FIELD_RESULT, "maxItems": 200}},
    (*MAPPING["required"], "field_mappings"),
)
SEARCH = obj({"query": STRING, "limit": LIMIT})
MAPPING_INPUT = {
    "datasource_gid": STRING,
    "name": STRING,
    "source_object": STRING,
    "target_binding_id": STRING,
    "field_mappings": {"type": "array", "items": FIELD, "maxItems": 200},
    "idempotency_key": IDEMPOTENCY,
}


_CONNECTOR_WRITE = {
    "name": STRING,
    "connector_type": STRING,
    "host": STRING,
    "port": {"type": "integer", "minimum": 1, "maximum": 65535},
    "database_name": STRING,
    "username": STRING,
    "credential_enrollment_handle": STRING,
    "credential_ref": STRING,
}
_ONE_CREDENTIAL = [{"required": [field], "not": {"required": [other]}} for field, other in (
    ("credential_enrollment_handle", "credential_ref"),
    ("credential_ref", "credential_enrollment_handle"),
)]


INPUT_SCHEMAS = {
    "integration.connector.create": obj(
        {**_CONNECTOR_WRITE, "idempotency_key": IDEMPOTENCY},
        ("name", "connector_type", "host", "port", "database_name", "username", "idempotency_key"),
        oneOf=_ONE_CREDENTIAL,
    ),
    "integration.connector.update": obj(
        {"gid": STRING, "expected_revision": POSITIVE, **_CONNECTOR_WRITE, "idempotency_key": IDEMPOTENCY},
        ("gid", "expected_revision", "idempotency_key"),
        **{"not": {"required": ["credential_enrollment_handle", "credential_ref"]}},
    ),
    "integration.connector.archive": obj({"gid": STRING, "expected_revision": POSITIVE}, ("gid", "expected_revision")),
    "integration.connector.search": SEARCH,
    "integration.connector.connection.test": obj(
        {"gid": STRING, "idempotency_key": IDEMPOTENCY}, ("gid", "idempotency_key")
    ),
    "integration.connector.schema.discover": obj({"gid": STRING, "limit": LIMIT}, ("gid",)),
    "integration.mapping.create": obj(
        MAPPING_INPUT,
        (
            "datasource_gid", "name", "source_object", "target_binding_id", "idempotency_key",
        ),
    ),
    "integration.mapping.update": obj(
        {"gid": STRING, "expected_revision": POSITIVE, "field_mappings": {"type": "array", "items": FIELD, "maxItems": 200}},
        ("gid", "expected_revision"),
    ),
    "integration.mapping.archive": obj({"gid": STRING, "expected_revision": POSITIVE}, ("gid", "expected_revision")),
    "integration.mapping.get": obj({"gid": STRING}, ("gid",)),
    "integration.mapping.search": obj(
        {"datasource_gid": STRING, "query": STRING, "limit": LIMIT}, ("datasource_gid",)
    ),
    "integration.mapping_target.search": obj(
        {
            "ontology_object_gids": {
                "type": "array", "items": STRING, "minItems": 1, "maxItems": 200,
                "uniqueItems": True,
            }
        },
        ("ontology_object_gids",),
    ),
    "integration.mapping_target.upsert": obj(
        {
            "binding_id": STRING, "ontology_object_gid": STRING,
            "target_domain": STRING, "target_capability_id": STRING,
            "target_major_version": POSITIVE, "minimum_catalog_release": STRING,
            "input_contract": STRING, "resource_gid": STRING,
            "target_expected_version": POSITIVE, "expected_revision": POSITIVE,
            "mapping_gid": STRING, "mapping_expected_revision": POSITIVE,
            "idempotency_key": IDEMPOTENCY,
        },
        (
            "binding_id", "ontology_object_gid", "target_domain", "target_capability_id",
            "target_major_version", "minimum_catalog_release", "input_contract",
            "resource_gid", "target_expected_version", "idempotency_key",
        ),
    ),
    "integration.field_mapping.search": obj({"mapping_gid": STRING, "limit": LIMIT}, ("mapping_gid",)),
    "integration.mapping.source_columns.discover": obj({"mapping_gid": STRING, "limit": LIMIT}, ("mapping_gid",)),
    "integration.mapping.preview": obj({"gid": STRING, "limit": LIMIT}, ("gid",)),
    "integration.field_mapping.batch.update": obj(
        {
            "mapping_gid": STRING,
            "expected_revision": POSITIVE,
            "items": {"type": "array", "items": FIELD, "minItems": 1, "maxItems": 200},
            "idempotency_key": IDEMPOTENCY,
        },
        ("mapping_gid", "expected_revision", "items", "idempotency_key"),
    ),
    "integration.mapping.import.start": obj(
        {"mapping_gid": STRING, "idempotency_key": IDEMPOTENCY},
        ("mapping_gid", "idempotency_key"),
    ),
    "integration.sync.start": obj({"mapping_gid": STRING}, ("mapping_gid",)),
}


OBJECT_RESULT = obj({"name": STRING, "kind": STRING}, ("name", "kind"))
COLUMN_RESULT = obj(
    {"name": STRING, "data_type": STRING, "nullable": {"type": "boolean"}},
    ("name", "data_type", "nullable"),
)
PREVIEW_CELL = obj(
    {
        "field": STRING,
        "value": {"type": ["string", "number", "integer", "boolean", "null"]},
        "redacted": {"type": "boolean"},
    },
    ("field", "value", "redacted"),
)
PREVIEW_ROW = obj({"values": {"type": "array", "items": PREVIEW_CELL, "maxItems": 200}}, ("values",))
MAPPING_TARGET = obj(
    {
        "ontology_object_gid": STRING,
        "binding_id": STRING,
        "target_domain": STRING,
        "target_capability_id": STRING,
        "target_major_version": POSITIVE,
        "minimum_catalog_release": STRING,
    },
    (
        "ontology_object_gid", "binding_id", "target_domain", "target_capability_id",
        "target_major_version", "minimum_catalog_release",
    ),
)


OUTPUT_SCHEMAS = {
    "integration.connector.create": CONNECTOR,
    "integration.connector.update": CONNECTOR,
    "integration.connector.archive": obj({"gid": STRING, "archived": {"type": "boolean"}}, ("gid", "archived")),
    "integration.connector.search": obj({"items": {"type": "array", "items": CONNECTOR, "maxItems": 200}}, ("items",)),
    "integration.connector.connection.test": obj(
        {"reachable": {"type": "boolean"}, "latency_ms": INTEGER, "message": STRING, "operation_ref": OPERATION_REF},
        ("operation_ref",),
    ),
    "integration.connector.schema.discover": obj(
        {"objects": {"type": "array", "items": OBJECT_RESULT, "maxItems": 200}, "operation_ref": OPERATION_REF},
        ("objects", "operation_ref"),
    ),
    "integration.mapping.create": MAPPING,
    "integration.mapping.update": obj(
        {"gid": STRING, "revision": POSITIVE, "changed": {"type": "boolean"}},
        ("gid", "revision", "changed"),
    ),
    "integration.mapping.archive": obj({"gid": STRING, "archived": {"type": "boolean"}}, ("gid", "archived")),
    "integration.mapping.get": MAPPING_DETAIL,
    "integration.mapping.search": obj({"items": {"type": "array", "items": MAPPING, "maxItems": 200}}, ("items",)),
    "integration.mapping_target.search": obj(
        {"items": {"type": "array", "items": MAPPING_TARGET, "maxItems": 200}}, ("items",)
    ),
    "integration.mapping_target.upsert": obj(
        {**MAPPING_TARGET["properties"], "resource_gid": STRING, "expected_version": POSITIVE, "revision": POSITIVE,
         "mapping_gid": STRING, "mapping_revision": POSITIVE},
        (*MAPPING_TARGET["required"], "resource_gid", "expected_version", "revision"),
    ),
    "integration.field_mapping.search": obj({"items": {"type": "array", "items": FIELD_RESULT, "maxItems": 200}}, ("items",)),
    "integration.mapping.source_columns.discover": obj(
        {"columns": {"type": "array", "items": COLUMN_RESULT, "maxItems": 200}, "operation_ref": OPERATION_REF},
        ("columns", "operation_ref"),
    ),
    "integration.mapping.preview": obj(
        {
            "rows": {"type": "array", "items": PREVIEW_ROW, "maxItems": 200},
            "truncated": {"type": "boolean"},
            "operation_ref": OPERATION_REF,
        },
        ("rows", "truncated", "operation_ref"),
    ),
    "integration.field_mapping.batch.update": obj(
        {
            "mapping_gid": STRING, "revision": POSITIVE, "updated_count": {"type": "integer", "minimum": 1, "maximum": 200},
            "items": {"type": "array", "items": FIELD_RESULT, "minItems": 1, "maxItems": 200},
        },
        ("mapping_gid", "revision", "updated_count", "items"),
    ),
    "integration.mapping.import.start": obj(
        {"run_id": STRING, "operation_ref": OPERATION_REF}, ("run_id", "operation_ref")
    ),
    "integration.sync.start": obj(
        {"run_id": STRING, "operation_ref": OPERATION_REF}, ("run_id", "operation_ref")
    ),
}


__all__ = ["INPUT_SCHEMAS", "OUTPUT_SCHEMAS"]
