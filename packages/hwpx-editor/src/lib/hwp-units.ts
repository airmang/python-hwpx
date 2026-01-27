/**
 * HWPX unit conversion utilities.
 *
 * HWPX uses hwpUnit where 7200 hwpUnit = 1 inch = 25.4 mm.
 * Screen rendering at 96 DPI: 1 hwpUnit = 96/7200 px ≈ 0.01333 px.
 */

const HWP_UNITS_PER_INCH = 7200;
const PX_PER_INCH = 96;
const MM_PER_INCH = 25.4;

/** Convert hwpUnit to pixels at 96 DPI. */
export function hwpToPx(hwpUnit: number): number {
  return (hwpUnit * PX_PER_INCH) / HWP_UNITS_PER_INCH;
}

/** Convert pixels (96 DPI) to hwpUnit. */
export function pxToHwp(px: number): number {
  return Math.round((px * HWP_UNITS_PER_INCH) / PX_PER_INCH);
}

/** Convert hwpUnit to millimeters. */
export function hwpToMm(hwpUnit: number): number {
  return (hwpUnit * MM_PER_INCH) / HWP_UNITS_PER_INCH;
}

/** Convert millimeters to hwpUnit. */
export function mmToHwp(mm: number): number {
  return Math.round((mm * HWP_UNITS_PER_INCH) / MM_PER_INCH);
}
