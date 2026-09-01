ALTER TABLE workmanship_base_capability_business_purposes
  MODIFY COLUMN definition_hash VARBINARY(71) NOT NULL;

ALTER TABLE workmanship_base_capability_business_rules
  MODIFY COLUMN definition_hash VARBINARY(71) NOT NULL;

ALTER TABLE workmanship_base_capability_relation_candidates
  MODIFY COLUMN candidate_hash VARBINARY(71) NOT NULL;

ALTER TABLE workmanship_base_capability_business_reviews
  MODIFY COLUMN definition_hash VARBINARY(71) NOT NULL;

ALTER TABLE workmanship_base_capability_rule_effectiveness
  MODIFY COLUMN definition_hash VARBINARY(71) NOT NULL;
