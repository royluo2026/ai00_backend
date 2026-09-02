-- Backfill independent VPPS socket requirement standards without rewriting legacy tool rows.
/* AI00: RESUMABLE BACKFILL */
INSERT INTO `workmanship_craft_resource_requirements`
  (`gid`,`resource_type`,`code`,`name`,`attributes`,`source`,`status`,`created_at`,`updated_at`)
SELECT
  UUID(), 'socket', `socket_code`, LEFT(COALESCE(NULLIF(`socket_model`, ''), `socket_code`), 255),
  JSON_OBJECT(
    'socket_model', `socket_model`,
    'socket_cad_no', `socket_cad_no`,
    'fastener_type', `fastener_type`,
    'fastener_params', `fastener_params`
  ),
  'legacy:vpps_tools.socket', `socket_status`, `first_created_at`, `first_created_at`
FROM (
  SELECT
    COALESCE(NULLIF(TRIM(`socket_model`), ''), NULLIF(TRIM(`socket_cad_no`), '')) AS `socket_code`,
    MAX(NULLIF(TRIM(`socket_model`), '')) AS `socket_model`,
    MAX(NULLIF(TRIM(`socket_cad_no`), '')) AS `socket_cad_no`,
    MAX(NULLIF(TRIM(`fastener_type`), '')) AS `fastener_type`,
    MAX(NULLIF(TRIM(`fastener_params`), '')) AS `fastener_params`,
    IF(SUM(`status` = 'active') > 0, 'active', 'retired') AS `socket_status`,
    MIN(`created_at`) AS `first_created_at`
  FROM `workmanship_tpl_vpps_tools`
  WHERE NULLIF(TRIM(`socket_model`), '') IS NOT NULL
     OR NULLIF(TRIM(`socket_cad_no`), '') IS NOT NULL
  GROUP BY COALESCE(NULLIF(TRIM(`socket_model`), ''), NULLIF(TRIM(`socket_cad_no`), ''))
) AS `legacy_sockets`
WHERE `socket_code` IS NOT NULL
ON DUPLICATE KEY UPDATE `resource_version`=`resource_version`;
