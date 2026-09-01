CREATE TABLE IF NOT EXISTS workmanship_base_capability_standard_review_requests (
  idempotency_key VARCHAR(255) NOT NULL,
  request_fingerprint VARCHAR(2048) NOT NULL,
  proposal_gid BIGINT NOT NULL,
  review_gid BIGINT NOT NULL,
  result_status VARCHAR(32) NOT NULL,
  result_row_version BIGINT NOT NULL,
  PRIMARY KEY (idempotency_key),
  CONSTRAINT fk_capability_standard_review_request_proposal FOREIGN KEY (proposal_gid)
    REFERENCES workmanship_base_capability_change_proposals (proposal_gid),
  CONSTRAINT fk_capability_standard_review_request_review FOREIGN KEY (review_gid)
    REFERENCES workmanship_base_capability_reviews (review_gid)
);
