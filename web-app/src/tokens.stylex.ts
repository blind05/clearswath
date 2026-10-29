// DESIGN.md's palette, type and breakpoint, for our own StyleX styles. Astryx gets the same values from theme.ts.
import * as stylex from "@stylexjs/stylex";

export const color = stylex.defineVars({
  ink: "#1E2B24",
  muted: "#5B6760",
  rule: "#D6DBD6",
  page: "#F2F4F1",
  panel: "#FFFFFF",
  clear: "#2E7D32",
  adjust: "#9A6200",
  stop: "#B42318",
  spray: "#C4127A",
  held: "#37474F",
  water: "#2B83BA",
});

export const font = stylex.defineVars({
  condensed: '"IBM Plex Sans Condensed", "Arial Narrow", sans-serif',
});

export const media = stylex.defineConsts({
  mobile: "@media (max-width: 799px)",
});
