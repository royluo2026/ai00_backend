CREATE TABLE IF NOT EXISTS workmanship_base_capability_business_review_requests (
  idempotency_key VARCHAR(255) NOT NULL,
  request_fingerprint VARCHAR(2048) NOT NULL,
  proposal_gid BIGINT NOT NULL,
  review_gid BIGINT NOT NULL,
  PRIMARY KEY (idempotency_key),
  CONSTRAINT fk_capability_business_review_request_proposal FOREIGN KEY (proposal_gid)
    REFERENCES workmanship_base_capability_change_proposals (proposal_gid),
  CONSTRAINT fk_capability_business_review_request_review FOREIGN KEY (review_gid)
    REFERENCES workmanship_base_capability_business_reviews (business_review_gid)
);
