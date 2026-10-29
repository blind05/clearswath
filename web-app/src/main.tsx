import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Theme } from "@astryxdesign/core/theme";
import "maplibre-gl/dist/maplibre-gl.css";
import "./index.css";
import { App } from "./App";
import { theme } from "./theme";

createRoot(document.getElementById("root")!).render(
  <StrictMode><Theme theme={theme} mode="light"><App /></Theme></StrictMode>,
);
