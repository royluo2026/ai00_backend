(function (root, factory) {
  const exports = factory();
  if (typeof module === 'object' && module.exports) module.exports = exports;
  if (root) root.OrthogonalRouter = exports;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  function routeOrthogonal(source, target, obstacles = []) {
    const forward = target.x >= source.x + source.w;
    const start = {
      x: forward ? source.x + source.w : source.x,
      y: source.y + source.h / 2,
    };
    const end = {
      x: forward ? target.x : target.x + target.w,
      y: target.y + target.h / 2,
    };
    const middleX = (start.x + end.x) / 2;
    // ponytail: deterministic dogleg; add obstacle detours when real layouts prove overlap.
    void obstacles;
    return [start, { x: middleX, y: start.y }, { x: middleX, y: end.y }, end];
  }

  function toSvgPath(points) {
    if (!points.length) return '';
    return `M ${points[0].x} ${points[0].y} ${points.slice(1).map(point => `L ${point.x} ${point.y}`).join(' ')}`;
  }

  return { routeOrthogonal, toSvgPath };
});
