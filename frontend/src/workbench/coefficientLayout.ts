/** Pixel widths are measured from the current 14px coefficient font, not source magnitudes. */
export interface CoefficientWidths { p: number; a: number; q: number; x: number; row: number }
export function coefficientLayout(width: number, requested: number, widths: CoefficientWidths) {
  if (!Number.isFinite(width) || width <= 0 || !Number.isFinite(requested) || requested < 1
    || Object.values(widths).some(value => !Number.isFinite(value) || value < 0)) return null;
  const compact = width < 640, pX = compact ? 36 : 48;
  const minimumP = Math.max(compact ? 50 : 40, Math.ceil(widths.p) + 14);
  const minimumA = Math.max(compact ? 58 : 40, Math.ceil(widths.a) + 14);
  const qWidth = Math.max(42, Math.ceil(widths.q) + 12), xWidth = Math.max(42, Math.ceil(widths.x) + 12);
  const rowWidth = Math.max(compact ? 70 : 64, Math.ceil(widths.row) + 18);
  const geometry = (count: number, stackVectors = false) => {
    const pCell = minimumP, vectorX = pX + count * pCell + 18;
    const xVectorX = stackVectors ? vectorX : vectorX + qWidth + 16;
    const braceX = stackVectors ? vectorX + Math.max(qWidth, xWidth) + 8 : xVectorX + xWidth + 8;
    const split = braceX + 26, matrixX = compact ? rowWidth + 18 : split + rowWidth;
    return { count, pX, pCell, vectorX, xVectorX, braceX, split, matrixX, stackVectors,
      cell: Math.min(130, (width - matrixX - 58) / count) };
  };
  const fits = (g: ReturnType<typeof geometry>) => g.cell >= minimumA
    && g.pX + g.count * g.pCell <= width - 18
    && g.vectorX + widths.q <= width - 18 && g.xVectorX + widths.x <= width - 18
    && g.braceX + 13 <= width - 8 && g.matrixX + g.count * g.cell + 43 <= width - 8;
  // Enumerate at most six windows; never shrink a label to make an extra column fit.
  for (let count = Math.min(Math.floor(requested), compact ? 2 : 6); count >= 1; count--) {
    const g = geometry(count);
    if (fits(g)) return g;
  }
  // One row fits above the existing compact A block when q and x use separate vertical bands.
  const stacked = compact ? geometry(1, true) : null;
  return stacked && fits(stacked) ? stacked : null;
}
