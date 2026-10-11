const LEVELS = Object.freeze([0.5, 0.75, 1, 1.25, 1.5]);

export const DEFAULT_TASK_CANVAS_ZOOM = 2;

export function stepTaskCanvasZoom(index, direction) {
  return Math.max(0, Math.min(LEVELS.length - 1, index + direction));
}

export function taskCanvasZoomView(index) {
  const scale = LEVELS[index];
  if (scale === undefined) throw new Error('invalid task canvas zoom');
  return { scale, width: `${900 * scale}px`, height: `${680 * scale}px`, label: `${scale * 100}%` };
}
