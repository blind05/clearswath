// The JSON the FastAPI app returns (app/pipeline.py to_json, plus the demo and agent fields from app/api.py).
import type { FeatureCollection, Geometry } from "geojson";

export type Status = "go" | "adjust" | "no-go";

export interface Reason {
  source: string;  // "label", "rule:water", "bulletin", "data"
  summary: string;
  kind?: string;  // "drift", "runoff" for some label reasons
  quote?: string;
  page?: number;
  target?: string;
  distance_ft?: number;
}

export interface LabelRule {
  kind: string; target: string | null; applies_to: string; value: number | null; unit: string | null;
  summary: string; quote: string; page: number; condition: string | null;
}

export interface ConfirmRule extends LabelRule { id: number; applied: boolean }

export interface TraceStep { tool?: string; note?: string; seconds?: number; result?: unknown }

export interface Overlay { url: string; bounds: [number, number, number, number]; credit?: string | null }

export interface Plan {
  run_id: string;
  status: Status;
  method: string;
  month: string;
  acres: { field_acres: number; spray_acres: number; excluded_acres: number };
  reasons: Reason[];
  warnings: string[];
  label: { product_name: string | null; epa_reg_no: string | null; rules: LabelRule[]; dropped: unknown[]; source: "pdf" | "image" };
  confirm: ConfirmRule[];
  excluded_rules: number[];
  bulletin: { in_pula: boolean; prohibited: boolean; citation: string; checked: boolean };
  imagery_date: string | null;
  water_source: string | null;
  weed_source?: string | null;
  scout: string[];
  spot?: { field_acres: number; treated_acres: number; clean_acres: number; buffered_acres: number; cell_size_m: number } | null;
  carrier_min?: { l_ha: number; quote: string; page: number } | null;
  layers: Record<string, FeatureCollection | Geometry>;
  demo?: { field: string; cached: boolean; month: string; overlay?: Overlay | null };
  answer?: string;
  trace?: TraceStep[];
  mode?: "agent" | "replay" | "pipeline";
  replay?: { model: string; date: string };
}

export interface PhotoResult {
  width: number; height: number; share_flagged: number; overlay_png: string; trained_on?: Record<string, number>;
}

export interface AppRecord {
  [field: string]: unknown;
  missing: string[];
  transcript: string;
  part137?: ({ [field: string]: unknown; missing: string[] }) | null;
}
