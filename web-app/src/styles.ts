// Text styles every panel shares. DESIGN.md's scale: 13 / 15 / 18 / 28 px.
import * as stylex from "@stylexjs/stylex";
import { color } from "./tokens.stylex";

export const text = stylex.create({
  small: { fontSize: 13, color: color.muted },
  h2: { fontSize: 15, fontWeight: 600, marginBottom: 8 },
  error: { fontWeight: 500, color: color.stop, paddingTop: 12 },
  num: { fontVariantNumeric: "tabular-nums" },
  stack: { display: "grid", gap: 12 },
});
