// Astryx themed from DESIGN.md: ink for actions, hairline rules, one 4 px radius, IBM Plex, light only.
import { defineTheme } from "@astryxdesign/core/theme";

const sans = '"IBM Plex Sans", system-ui, sans-serif';

export const theme = defineTheme({
  name: "clearswath",
  tokens: {
    "--font-family-body": sans,
    "--font-family-heading": sans,
    "--font-size-base": "0.9375rem",
    "--font-size-sm": "0.8125rem",
    "--color-accent": "#1E2B24",
    "--color-on-accent": "#FFFFFF",
    "--color-text-primary": "#1E2B24",
    "--color-text-secondary": "#5B6760",
    "--color-text-accent": "#1E2B24",
    "--color-icon-primary": "#1E2B24",
    "--color-icon-secondary": "#5B6760",
    "--color-border": "#D6DBD6",
    "--color-border-emphasized": "#B5BDB6",
    "--color-background-body": "#F2F4F1",
    "--color-background-surface": "#FFFFFF",
    "--color-background-card": "#FFFFFF",
    "--color-background-popover": "#FFFFFF",
    "--color-error": "#B42318",
    "--color-warning": "#9A6200",
    "--color-success": "#2E7D32",
    "--radius-element": "4px",
    "--radius-container": "4px",
    "--radius-inner": "2px",
    "--radius-page": "4px",
    "--focus-outline-color": "#1E2B24",
    "--focus-outline-offset": "2px",
  },
});
