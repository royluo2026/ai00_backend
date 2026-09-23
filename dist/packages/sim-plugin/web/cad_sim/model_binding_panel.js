(function (root) {
  'use strict';
  const MIME = 'application/x-ai00-vm-occurrence';
  function writeDrag(event, occurrence) {
    const payload = {
      occurrence_gid: String(occurrence.occurrence_gid),
      kind: occurrence.kind,
      model_number: occurrence.model_number || '',
    };
    event.dataTransfer.setData(MIME, JSON.stringify(payload));
    event.dataTransfer.effectAllowed = 'copyMove';
  }
  function readDrop(event) {
    const raw = event.dataTransfer.getData(MIME);
    if (!raw) return null;
    const value = JSON.parse(raw);
    if (!/^\d+$/.test(value.occurrence_gid)) throw new Error('occurrence_gid_invalid');
    return value;
  }
  root.AI00SimulationModelBinding = { MIME, readDrop, writeDrag };
})(globalThis);
