-- One-way, replay-safe cutover from the legacy Factory compatibility tables.

/* AI00: RESUMABLE BACKFILL */
INSERT INTO `workmanship_factory_structures`
  (`gid`,`kind`,`name`,`parent_gid`,`tenant_gid`,`version`,`archived`,`attributes`,`created_at`)
SELECT
  `gid`, 'factory', `name`, NULL,
  COALESCE(NULLIF(`team_id`, ''), 'legacy:unassigned'),
  1, FALSE, COALESCE(`meta`, JSON_OBJECT()), `created_at`
FROM `workmanship_factory_factories`
ON DUPLICATE KEY UPDATE `version`=`version`;

/* AI00: RESUMABLE BACKFILL */
INSERT INTO `workmanship_factory_structures`
  (`gid`,`kind`,`name`,`parent_gid`,`tenant_gid`,`version`,`archived`,`attributes`,`created_at`)
SELECT
  `gid`, 'section', `name`, `factory_gid`,
  COALESCE(NULLIF((SELECT `team_id` FROM `workmanship_factory_factories`
                   WHERE `gid`=`factory_gid` LIMIT 1), ''), 'legacy:unassigned'),
  1, FALSE,
  JSON_OBJECT('sort_order', `sort_order`, 'color', `color`,
              'canvas_x', `canvas_x`, 'canvas_y', `canvas_y`,
              'canvas_w', `canvas_w`, 'canvas_h', `canvas_h`),
  `created_at`
FROM `workmanship_factory_factory_sections`
ON DUPLICATE KEY UPDATE `version`=`version`;

/* AI00: RESUMABLE BACKFILL */
INSERT INTO `workmanship_factory_structures`
  (`gid`,`kind`,`name`,`parent_gid`,`tenant_gid`,`version`,`archived`,`attributes`,`created_at`)
SELECT
  `gid`, 'line', `name`, `factory_gid`,
  COALESCE(NULLIF((SELECT `team_id` FROM `workmanship_factory_factories`
                   WHERE `gid`=`factory_gid` LIMIT 1), ''), 'legacy:unassigned'),
  1, FALSE, COALESCE(`meta`, JSON_OBJECT()), `created_at`
FROM `workmanship_factory_factory_lines`
ON DUPLICATE KEY UPDATE `version`=`version`;

/* AI00: RESUMABLE BACKFILL */
INSERT INTO `workmanship_factory_structures`
  (`gid`,`kind`,`name`,`parent_gid`,`tenant_gid`,`version`,`archived`,`attributes`,`created_at`)
SELECT
  `gid`, 'station', `name`, `factory_section_gid`,
  COALESCE(NULLIF((SELECT `team_id` FROM `workmanship_factory_factories`
                   WHERE `gid`=(SELECT `factory_gid` FROM `workmanship_factory_factory_sections`
                                WHERE `gid`=`factory_section_gid` LIMIT 1) LIMIT 1), ''),
           'legacy:unassigned'),
  1, FALSE,
  JSON_OBJECT('code', `code`, 'canvas_x', `canvas_x`,
              'canvas_y', `canvas_y`, 'takt_time', `takt_time`,
              'height_mm', `height_mm`, 'legacy_meta', `meta`),
  `created_at`
FROM `workmanship_factory_factory_stations`
ON DUPLICATE KEY UPDATE `version`=`version`;
