-- Keep authenticated App adapter compatibility evidence with its runtime session.
ALTER TABLE `workmanship_sim_connector_runtime_devices`
  ADD COLUMN IF NOT EXISTS `adapter_health_json` JSON NULL;
