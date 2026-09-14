-- Parsed product tree for an imported immutable PLMXML document.
-- Dependency signature changes when a referenced PLMXML version is replaced.
CREATE TABLE IF NOT EXISTS `workmanship_sim_plmxml_product_tree_cache` (
  `document_gid` BIGINT UNSIGNED NOT NULL,
  `dependency_signature` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `algorithm_version` VARCHAR(64) NOT NULL,
  `source_sha256` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `payload_json` LONGTEXT NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`document_gid`,`dependency_signature`,`algorithm_version`),
  CONSTRAINT `fk_sim_plmxml_tree_document` FOREIGN KEY (`document_gid`)
    REFERENCES `workmanship_sim_vm_documents` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
