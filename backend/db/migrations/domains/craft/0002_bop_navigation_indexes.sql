-- Bounded keyset navigation for large BOP versions. Craft owns these indexes.
CREATE INDEX `idx_bop_nav_type_order`
  ON `workmanship_bop_bop_entries`
  (`version_gid`, `is_deleted`, `node_type`(64), `sort_order`, `gid`);

CREATE INDEX `idx_bop_nav_parent_order`
  ON `workmanship_bop_bop_entries`
  (`version_gid`, `is_deleted`, `parent_gid`, `sort_order`, `gid`);

CREATE INDEX `idx_bop_nav_links_page`
  ON `workmanship_bop_bop_entry_links`
  (`version_gid`, `is_deleted`, `entry_gid`);
