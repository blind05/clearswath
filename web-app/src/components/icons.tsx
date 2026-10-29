// The four marks the UI components need, drawn here instead of pulling in an icon library.
import type { SVGProps } from "react";

const base = { width: 16, height: 16, viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: 1.6,
               "aria-hidden": true } as const;

export const CheckIcon = (p: SVGProps<SVGSVGElement>) => <svg {...base} {...p}><path d="M3 8.5l3 3 7-7" /></svg>;
export const ChevronDownIcon = (p: SVGProps<SVGSVGElement>) => <svg {...base} {...p}><path d="M4 6l4 4 4-4" /></svg>;
export const ChevronUpIcon = (p: SVGProps<SVGSVGElement>) => <svg {...base} {...p}><path d="M4 10l4-4 4 4" /></svg>;
export const XIcon = (p: SVGProps<SVGSVGElement>) => <svg {...base} {...p}><path d="M4 4l8 8M12 4l-8 8" /></svg>;
