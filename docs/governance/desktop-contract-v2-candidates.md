# Desktop contract major 2 candidates

These four Provider registrations are unpublished. The published Catalog and its 575 generated pages remain unchanged because the full release has 16 existing Knowledge collection blockers. No business approval or runtime success is asserted.

Major 1 descriptors are frozen by `backend/tests/fixtures/desktop_contract_v1.json`. Tests verify the complete descriptors, major 2 request fields, wrong types, unknown fields, collection separation and result projections.

The schemas add named legacy request-model fields only. Untyped nested JSON remains closed and is listed in the candidate artifact as unresolved business-schema debt.

## craft.library.change.apply@2

Provider: `craft`. User confirmation retained; library v2 adds a closed operation-discriminated adapter over the existing business handler.

```json
{
  "oneOf": [
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "tools.create"
        },
        "record": {
          "type": "object",
          "properties": {
            "vpps": {
              "type": [
                "string",
                "null"
              ]
            },
            "name": {
              "type": "string"
            },
            "gun_model": {
              "type": "string"
            },
            "matou_part_no": {
              "type": "string"
            },
            "importance": {
              "type": "string"
            },
            "gun_type": {
              "type": "string"
            },
            "wireless": {
              "type": "string"
            },
            "output_square": {
              "type": "string"
            },
            "torque_min": {
              "type": "string"
            },
            "torque_recommended": {
              "type": "string"
            },
            "cad_model_no": {
              "type": "string"
            },
            "socket_model": {
              "type": "string"
            },
            "fastener_type": {
              "type": "string"
            },
            "fastener_params": {
              "type": "string"
            },
            "extension_model": {
              "type": "string"
            },
            "socket_cad_no": {
              "type": "string"
            },
            "extension_cad_no": {
              "type": "string"
            }
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "record"
      ]
    },
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "tools.update"
        },
        "gid": {
          "type": "string",
          "minLength": 1,
          "maxLength": 128
        },
        "record": {
          "type": "object",
          "properties": {
            "vpps": {
              "type": [
                "string",
                "null"
              ]
            },
            "name": {
              "type": "string"
            },
            "gun_model": {
              "type": "string"
            },
            "matou_part_no": {
              "type": "string"
            },
            "importance": {
              "type": "string"
            },
            "gun_type": {
              "type": "string"
            },
            "wireless": {
              "type": "string"
            },
            "output_square": {
              "type": "string"
            },
            "torque_min": {
              "type": "string"
            },
            "torque_recommended": {
              "type": "string"
            },
            "cad_model_no": {
              "type": "string"
            },
            "socket_model": {
              "type": "string"
            },
            "fastener_type": {
              "type": "string"
            },
            "fastener_params": {
              "type": "string"
            },
            "extension_model": {
              "type": "string"
            },
            "socket_cad_no": {
              "type": "string"
            },
            "extension_cad_no": {
              "type": "string"
            }
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "gid",
        "record"
      ]
    },
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "equipments.create"
        },
        "record": {
          "type": "object",
          "properties": {
            "name": {
              "type": "string"
            },
            "category": {
              "type": "string"
            },
            "spec": {
              "type": "object",
              "properties": {},
              "additionalProperties": false,
              "maxProperties": 0
            }
          },
          "additionalProperties": false,
          "required": [
            "name"
          ]
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "record"
      ]
    },
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "equipments.update"
        },
        "gid": {
          "type": "string",
          "minLength": 1,
          "maxLength": 128
        },
        "record": {
          "type": "object",
          "properties": {
            "name": {
              "type": [
                "string",
                "null"
              ]
            },
            "category": {
              "type": [
                "string",
                "null"
              ]
            },
            "spec": {
              "type": [
                "object",
                "null"
              ],
              "properties": {},
              "additionalProperties": false,
              "maxProperties": 0
            }
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "gid",
        "record"
      ]
    },
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "fixtures.create"
        },
        "record": {
          "type": "object",
          "properties": {
            "name": {
              "type": "string"
            },
            "category": {
              "type": "string"
            },
            "spec": {
              "type": "object",
              "properties": {},
              "additionalProperties": false,
              "maxProperties": 0
            }
          },
          "additionalProperties": false,
          "required": [
            "name"
          ]
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "record"
      ]
    },
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "fixtures.update"
        },
        "gid": {
          "type": "string",
          "minLength": 1,
          "maxLength": 128
        },
        "record": {
          "type": "object",
          "properties": {
            "name": {
              "type": [
                "string",
                "null"
              ]
            },
            "category": {
              "type": [
                "string",
                "null"
              ]
            },
            "spec": {
              "type": [
                "object",
                "null"
              ],
              "properties": {},
              "additionalProperties": false,
              "maxProperties": 0
            }
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "gid",
        "record"
      ]
    },
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "fasteners.create"
        },
        "record": {
          "type": "object",
          "properties": {
            "fastener_type": {
              "type": "string"
            },
            "part_no": {
              "type": "string"
            },
            "name": {
              "type": "string"
            },
            "thread_spec": {
              "type": "string"
            },
            "model": {
              "type": "string"
            },
            "shank_length": {
              "type": "string"
            },
            "guide_type": {
              "type": "string"
            },
            "guide_length": {
              "type": "string"
            },
            "has_adhesive": {
              "type": "string"
            },
            "drive_size": {
              "type": "string"
            },
            "flange_diameter": {
              "type": "string"
            },
            "first_vehicle": {
              "type": "string"
            }
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "record"
      ]
    },
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "fasteners.update"
        },
        "gid": {
          "type": "string",
          "minLength": 1,
          "maxLength": 128
        },
        "record": {
          "type": "object",
          "properties": {
            "fastener_type": {
              "type": [
                "string",
                "null"
              ]
            },
            "part_no": {
              "type": [
                "string",
                "null"
              ]
            },
            "name": {
              "type": [
                "string",
                "null"
              ]
            },
            "thread_spec": {
              "type": [
                "string",
                "null"
              ]
            },
            "model": {
              "type": [
                "string",
                "null"
              ]
            },
            "shank_length": {
              "type": [
                "string",
                "null"
              ]
            },
            "guide_type": {
              "type": [
                "string",
                "null"
              ]
            },
            "guide_length": {
              "type": [
                "string",
                "null"
              ]
            },
            "has_adhesive": {
              "type": [
                "string",
                "null"
              ]
            },
            "drive_size": {
              "type": [
                "string",
                "null"
              ]
            },
            "flange_diameter": {
              "type": [
                "string",
                "null"
              ]
            },
            "first_vehicle": {
              "type": [
                "string",
                "null"
              ]
            }
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "gid",
        "record"
      ]
    },
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "part_names.create"
        },
        "record": {
          "type": "object",
          "properties": {
            "vpps_description": {
              "type": "string"
            },
            "part_category": {
              "type": "string"
            },
            "description": {
              "type": "string"
            },
            "level": {
              "type": "string"
            },
            "vpps_desc_cn": {
              "type": "string"
            },
            "vpps": {
              "type": [
                "string",
                "null"
              ]
            },
            "importance": {
              "type": "string"
            },
            "vehicle_model": {
              "type": "string"
            },
            "parent_vpps": {
              "type": "string"
            },
            "status": {
              "type": "string"
            },
            "meta": {
              "type": "object",
              "properties": {
                "added_by": {
                  "type": "string",
                  "maxLength": 2000
                },
                "project": {
                  "type": "string",
                  "maxLength": 2000
                },
                "added_at": {
                  "type": "string",
                  "maxLength": 2000
                }
              },
              "additionalProperties": false
            },
            "flex_type": {
              "type": "string"
            },
            "ref_main_vpps": {
              "type": "string"
            },
            "ref_main_vpps_desc": {
              "type": "string"
            },
            "ref_install_direction": {
              "type": "string"
            },
            "ref_static_clearance": {
              "type": "string"
            },
            "ref_install_clearance": {
              "type": "string"
            },
            "alias": {
              "type": "array",
              "items": {
                "type": "string",
                "maxLength": 2000
              },
              "maxItems": 200
            }
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "record"
      ]
    },
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "part_names.update"
        },
        "gid": {
          "type": "string",
          "minLength": 1,
          "maxLength": 128
        },
        "record": {
          "type": "object",
          "properties": {
            "vpps_description": {
              "type": "string"
            },
            "part_category": {
              "type": "string"
            },
            "description": {
              "type": "string"
            },
            "level": {
              "type": "string"
            },
            "vpps_desc_cn": {
              "type": "string"
            },
            "vpps": {
              "type": [
                "string",
                "null"
              ]
            },
            "importance": {
              "type": "string"
            },
            "vehicle_model": {
              "type": "string"
            },
            "parent_vpps": {
              "type": "string"
            },
            "status": {
              "type": "string"
            },
            "meta": {
              "type": "object",
              "properties": {
                "added_by": {
                  "type": "string",
                  "maxLength": 2000
                },
                "project": {
                  "type": "string",
                  "maxLength": 2000
                },
                "added_at": {
                  "type": "string",
                  "maxLength": 2000
                }
              },
              "additionalProperties": false
            },
            "flex_type": {
              "type": "string"
            },
            "ref_main_vpps": {
              "type": "string"
            },
            "ref_main_vpps_desc": {
              "type": "string"
            },
            "ref_install_direction": {
              "type": "string"
            },
            "ref_static_clearance": {
              "type": "string"
            },
            "ref_install_clearance": {
              "type": "string"
            },
            "alias": {
              "type": "array",
              "items": {
                "type": "string",
                "maxLength": 2000
              },
              "maxItems": 200
            }
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "gid",
        "record"
      ]
    },
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "tools.delete"
        },
        "gid": {
          "type": "string",
          "minLength": 1,
          "maxLength": 128
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "gid"
      ]
    },
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "tools.obsolete"
        },
        "gid": {
          "type": "string",
          "minLength": 1,
          "maxLength": 128
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "gid"
      ]
    },
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "equipments.obsolete"
        },
        "gid": {
          "type": "string",
          "minLength": 1,
          "maxLength": 128
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "gid"
      ]
    },
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "fixtures.obsolete"
        },
        "gid": {
          "type": "string",
          "minLength": 1,
          "maxLength": 128
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "gid"
      ]
    },
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "fasteners.delete"
        },
        "gid": {
          "type": "string",
          "minLength": 1,
          "maxLength": 128
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "gid"
      ]
    },
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "part_names.delete"
        },
        "gid": {
          "type": "string",
          "minLength": 1,
          "maxLength": 128
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "gid"
      ]
    },
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "part_names.batch_add_from_pbom"
        },
        "items": {
          "type": "array",
          "maxItems": 500,
          "items": {
            "type": "object",
            "properties": {
              "vpps": {
                "type": "string",
                "maxLength": 2000
              },
              "vpps_desc_cn": {
                "type": "string",
                "maxLength": 2000
              },
              "vpps_description": {
                "type": "string",
                "maxLength": 2000
              }
            },
            "additionalProperties": false,
            "required": [
              "vpps"
            ]
          }
        },
        "meta": {
          "type": "object",
          "properties": {
            "added_by": {
              "type": "string",
              "maxLength": 2000
            },
            "project": {
              "type": "string",
              "maxLength": 2000
            },
            "added_at": {
              "type": "string",
              "maxLength": 2000
            }
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "items"
      ]
    },
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "part_names.batch_accept_alias"
        },
        "items": {
          "type": "array",
          "maxItems": 500,
          "items": {
            "type": "object",
            "properties": {
              "vpps_part_gid": {
                "type": "string",
                "minLength": 1,
                "maxLength": 128
              },
              "alias": {
                "type": "string",
                "maxLength": 2000
              },
              "pbom_part_gid": {
                "type": "string",
                "maxLength": 2000
              }
            },
            "additionalProperties": false,
            "required": [
              "vpps_part_gid",
              "alias"
            ]
          }
        },
        "meta": {
          "type": "object",
          "properties": {
            "added_by": {
              "type": "string",
              "maxLength": 2000
            },
            "project": {
              "type": "string",
              "maxLength": 2000
            },
            "added_at": {
              "type": "string",
              "maxLength": 2000
            }
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "items"
      ]
    },
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "part_names.accept_alias"
        },
        "gid": {
          "type": "string",
          "minLength": 1,
          "maxLength": 128
        },
        "alias": {
          "type": "string",
          "maxLength": 2000
        },
        "record": {
          "type": "object",
          "properties": {
            "pbom_part_gid": {
              "type": [
                "string",
                "null"
              ],
              "maxLength": 128
            }
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "gid",
        "alias"
      ]
    }
  ]
}
```

## craft.rule.library.change.apply@2

Provider: `craft`. User confirmation retained; library v2 adds a closed operation-discriminated adapter over the existing business handler.

```json
{
  "oneOf": [
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "create"
        },
        "gid": {
          "type": "string",
          "minLength": 1
        },
        "record": {
          "type": "object",
          "properties": {
            "code": {
              "type": "string"
            },
            "name": {
              "type": "string"
            },
            "rule_type": {
              "type": "string"
            },
            "enforcement_level": {
              "type": "string"
            },
            "status": {
              "type": "string"
            },
            "share_scope": {
              "type": "string"
            },
            "list_gid": {
              "type": [
                "string",
                "null"
              ]
            },
            "context_class_gid": {
              "type": [
                "string",
                "null"
              ]
            },
            "rule_definition": {
              "type": "object",
              "properties": {},
              "additionalProperties": false
            }
          },
          "additionalProperties": false,
          "required": [
            "name"
          ]
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "record"
      ]
    },
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "update"
        },
        "gid": {
          "type": "string",
          "minLength": 1
        },
        "record": {
          "type": "object",
          "properties": {
            "code": {
              "type": "string"
            },
            "name": {
              "type": "string"
            },
            "rule_type": {
              "type": "string"
            },
            "enforcement_level": {
              "type": "string"
            },
            "status": {
              "type": "string"
            },
            "share_scope": {
              "type": "string"
            },
            "list_gid": {
              "type": [
                "string",
                "null"
              ]
            },
            "context_class_gid": {
              "type": [
                "string",
                "null"
              ]
            },
            "rule_definition": {
              "type": "object",
              "properties": {},
              "additionalProperties": false
            },
            "expression": {
              "type": "string"
            }
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "gid",
        "record"
      ]
    },
    {
      "type": "object",
      "properties": {
        "operation": {
          "const": "delete"
        },
        "gid": {
          "type": "string",
          "minLength": 1
        },
        "record": {
          "type": "object",
          "properties": {
            "code": {
              "type": "string"
            },
            "name": {
              "type": "string"
            },
            "rule_type": {
              "type": "string"
            },
            "enforcement_level": {
              "type": "string"
            },
            "status": {
              "type": "string"
            },
            "share_scope": {
              "type": "string"
            },
            "list_gid": {
              "type": [
                "string",
                "null"
              ]
            },
            "context_class_gid": {
              "type": [
                "string",
                "null"
              ]
            },
            "rule_definition": {
              "type": "object",
              "properties": {},
              "additionalProperties": false
            },
            "expression": {
              "type": "string"
            }
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false,
      "required": [
        "operation",
        "gid"
      ]
    }
  ]
}
```

## project.task.change.apply.atomic.tasks_create@2

Provider: `project_management`. User confirmation retained; library v2 adds a closed operation-discriminated adapter over the existing business handler.

```json
{
  "type": "object",
  "properties": {
    "arguments": {
      "type": "object",
      "properties": {
        "title": {
          "type": "string"
        },
        "description": {
          "type": "string"
        },
        "owner_gid": {
          "type": "string"
        },
        "assignee_team_gid": {
          "type": [
            "string",
            "null"
          ]
        },
        "project_gid": {
          "type": [
            "string",
            "null"
          ]
        },
        "status": {
          "type": "string"
        },
        "priority": {
          "type": "string"
        },
        "source_ref": {
          "type": "object",
          "properties": {},
          "additionalProperties": false
        },
        "review_date": {
          "type": [
            "string",
            "null"
          ]
        },
        "meeting_level": {
          "type": "string"
        },
        "meeting_doc_link": {
          "type": [
            "string",
            "null"
          ]
        },
        "progress_logs": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {},
            "additionalProperties": false
          },
          "maxItems": 200
        },
        "due_date": {
          "type": [
            "string",
            "null"
          ]
        },
        "plan_start": {
          "type": [
            "string",
            "null"
          ]
        },
        "plan_end": {
          "type": [
            "string",
            "null"
          ]
        },
        "actual_start": {
          "type": [
            "string",
            "null"
          ]
        },
        "actual_end": {
          "type": [
            "string",
            "null"
          ]
        },
        "share_scope": {
          "type": "string"
        },
        "list_gid": {
          "type": [
            "string",
            "null"
          ]
        },
        "local_gid": {
          "type": [
            "string",
            "null"
          ]
        },
        "local_created_at": {
          "type": [
            "number",
            "null"
          ]
        },
        "attachments": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {},
            "additionalProperties": false
          },
          "maxItems": 200
        },
        "scheduled_date": {
          "type": [
            "string",
            "null"
          ]
        },
        "scheduled_start_time": {
          "type": [
            "string",
            "null"
          ]
        },
        "time_estimate": {
          "type": [
            "integer",
            "null"
          ]
        },
        "is_deleted": {
          "type": "boolean"
        },
        "parent_task_gid": {
          "type": [
            "string",
            "null"
          ]
        },
        "canvas_x": {
          "type": [
            "number",
            "null"
          ]
        },
        "canvas_y": {
          "type": [
            "number",
            "null"
          ]
        },
        "completion": {
          "type": "integer"
        },
        "node_type": {
          "type": "string"
        },
        "canvas_icon": {
          "type": "string"
        },
        "feishu_assignee_open_id": {
          "type": [
            "string",
            "null"
          ]
        },
        "feishu_assignee_name": {
          "type": [
            "string",
            "null"
          ]
        },
        "feishu_group_chat_id": {
          "type": [
            "string",
            "null"
          ]
        },
        "feishu_group_name": {
          "type": [
            "string",
            "null"
          ]
        },
        "feishu_groups": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {},
            "additionalProperties": false
          },
          "maxItems": 200
        },
        "feishu_docs": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {},
            "additionalProperties": false
          },
          "maxItems": 200
        }
      },
      "additionalProperties": false,
      "required": [
        "title"
      ]
    }
  },
  "additionalProperties": false,
  "required": [
    "arguments"
  ]
}
```

## project.issue.change.apply.atomic.issues_create@2

Provider: `project_management`. User confirmation retained; library v2 adds a closed operation-discriminated adapter over the existing business handler.

```json
{
  "type": "object",
  "properties": {
    "arguments": {
      "type": "object",
      "properties": {
        "title": {
          "type": "string"
        },
        "description": {
          "type": "string"
        },
        "severity": {
          "type": "string"
        },
        "status": {
          "type": "string"
        },
        "owner_gid": {
          "type": "string"
        },
        "assignee_team_gid": {
          "type": [
            "string",
            "null"
          ]
        },
        "project_gid": {
          "type": [
            "string",
            "null"
          ]
        },
        "tracking_refs": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {},
            "additionalProperties": false
          },
          "maxItems": 200
        },
        "occurrence_root_cause": {
          "type": [
            "string",
            "null"
          ]
        },
        "escape_root_cause": {
          "type": [
            "string",
            "null"
          ]
        },
        "interim_action": {
          "type": [
            "string",
            "null"
          ]
        },
        "permanent_action": {
          "type": [
            "string",
            "null"
          ]
        },
        "source_ref": {
          "type": "object",
          "properties": {},
          "additionalProperties": false
        },
        "related_task_gid": {
          "type": [
            "string",
            "null"
          ]
        },
        "related_knowledge_gid": {
          "type": [
            "string",
            "null"
          ]
        },
        "approval_order_gid": {
          "type": [
            "string",
            "null"
          ]
        },
        "bop_entry_gid": {
          "type": [
            "string",
            "null"
          ]
        },
        "share_scope": {
          "type": "string"
        },
        "list_gid": {
          "type": [
            "string",
            "null"
          ]
        },
        "attachments": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {},
            "additionalProperties": false
          },
          "maxItems": 200
        },
        "feishu_assignee_open_id": {
          "type": [
            "string",
            "null"
          ]
        },
        "feishu_assignee_name": {
          "type": [
            "string",
            "null"
          ]
        },
        "feishu_group_chat_id": {
          "type": [
            "string",
            "null"
          ]
        },
        "feishu_group_name": {
          "type": [
            "string",
            "null"
          ]
        },
        "feishu_groups": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {},
            "additionalProperties": false
          },
          "maxItems": 200
        },
        "feishu_docs": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {},
            "additionalProperties": false
          },
          "maxItems": 200
        }
      },
      "additionalProperties": false,
      "required": [
        "title"
      ]
    }
  },
  "additionalProperties": false,
  "required": [
    "arguments"
  ]
}
```
