# Module contracts

Shapes are shapely geometries in EPSG:4326 (lon/lat) unless stated. Areas in acres.
Don't change a contract unless the human asks.

| Module | Function | Takes | Returns |
| --- | --- | --- | --- |
| `app/llm.py` | `client(provider)`, `chat()`, `chat_json()`, `sam_raw()`, `transcribe()`, `data_url()`, `load_prompt()`, `resolve_provider()` | messages, JSON schema (object root), optional `provider` (`meta` or `baseten`, default `LLM_PROVIDER`) | model reply; dict matching schema (on Baseten via one forced tool call). Logs every call to `data/logs/calls.jsonl` |
| `app/geo.py` | `load_field()`, `check_field()`, `save_shapes()`, `load_shapes()`, `to_feature_collection()` | GeoJSON paths, shapes | shapely shapes in EPSG:4326; GeoJSON dicts. `load_field` raises `FieldError` unless the field is a valid polygon in the contiguous US, <= 640 acres (`MAX_FIELD_ACRES`) and <= 2,000 points; `pipeline.run` and `agent.run` check it before any paid call |
| `app/imagery.py` | `fetch_tile(field_path, out_png)` | field GeoJSON | PNG plus `.json` sidecar: crs, transform (6 values, downscaled), date (newest), dates, empty_fraction, width, height. Gaps are filled from other NAIP images |
| `app/imagery.py` | `usgs_water(field_path)` | field GeoJSON, optional `failed` list | list of water shapes; names of layers that errored are appended to `failed` |
| `app/segment.py` | `find_hazards(field_path)` | field GeoJSON | `{water, building, habitat, imagery_date, water_source, water_warnings, imagery_warnings}`; cached per field and hazard |
| `app/label_reader.py` | `read_label(path, provider=None)` (= `verify(read_raw(path, provider))`) | PDF or image | `LabelRules`: product_name, epa_reg_no, rules (kind, target, applies_to, value, unit, summary, quote, page, condition), dropped, source |
| `app/bulletins.py` | `check_bulletin(field_path, month, reg_no)` | field, month, product | `{in_pula, prohibited, limitations, restricted, citation, checked}` |
| `app/buffers.py` | `plan(field, hazards, rules, restricted, method, prohibited, gaps=(), managed=(), wind_from_deg=None)`, `drift_zone(...)` | shapes and rules; land the user marked as managed; optional wind direction | `{status, method, field_acres, spray_acres, excluded_acres, spray_zone, no_spray, reasons}` |
| `app/cells.py` | `grid(field_m, size_m)`, `classify(field, weeds, no_spray, size_m, threshold=0.01)`, `summary(result)` | field, weed shapes, the no-spray union, cell size (m) | cells with `cover` and `state` (`spray`, `clean`, `buffered`; buffered always wins), acres by state and a SHA-256 of the inputs. No model calls |
| `app/pipeline.py` | `run(field_path, label_path, month, method, excluded_rules=())`, `assemble(...)`, `to_json(result)`, `save_inputs()`/`load_inputs()` (demo cache) | paths and options; ids of rules the user unticked; optional `hazards["weeds"]` (weed map) | full result, with `cells` (1 m spot-spray grid; a no-go plan sprays no cells) when there is a weed map; JSON with map layers (`spray_cells`, `buffered_cells`), `spot` acres, `confirm` and `excluded_rules` for the page |
| `app/spend.py` | `cost(model, usage)`, `record(model, usage)`, `today()` | a call's model and token usage | estimated USD; today's total (UTC) in `data/logs/spend.json`. No network |
| `app/exports.py` | `spot_raster(grid)`, `write_spot_tif(grid, path)`, `dji_zip(field, spot_tif, rate)` | the cell grid; rate per ha | GeoTIFF on the cell grid (1 spray, 0 not, 255 outside); zip with `DJI/ShapeFile/boundary.*` and `DJI/Rx/prescription.tif` (layout TODO(verify) on a controller). No model calls |
| `app/agent.py` | `run(field_path, label_path, month, method, excluded_rules=(), provider=None)` | same | `{run_id, answer, decision, trace, mode, result}`; `result` is what `pipeline.run` returns |
| `app/records.py` | `transcribe(path)`, `fill_record(text, job)` | audio; transcript and job dict | text; `AppRecord` with `missing` list; drone/aerial jobs add `part137` (14 CFR 137.71 items, own `missing` list) |
| `app/api.py` | `/api/demo`, `/api/demo/image/{name}`, `/api/label`, `/api/plan`, `/api/agent`, `/api/kml/{id}`, `/api/export/{id}/{dji,geojson}`, `/api/record` | form uploads | JSON for `web/index.html` |

Drift rules (engine rule 2) buffer the treated area toward unmanaged land: everything outside the field that
the user hasn't marked as managed (`hazards["managed"]`), in every direction, or downwind only when a wind
direction is given. Unmanaged gaps under 0.5 m are ignored as drawing noise. A drift or buffer rule whose quote
fails the check is a `gap` (NO-GO).

Every label rule is applied. Buffer rules with a `condition` (e.g. "ULV aerial only"), and every rule
read from a photo, are listed in `confirm`; the user can untick them (`excluded_rules`, ids = indexes into
`label.rules`). Unticking anything else is refused. A model's condition can only make the plan stricter.

Paid endpoints (`/api/plan`, `/api/agent`, `/api/label`, `/api/record`) need the `X-Access-Code` header when
`ACCESS_CODE` is set (refused on Render without one), plus 3 live runs per IP per day (`RUNS_PER_IP_PER_DAY`),
a daily run cap (`DAILY_RUN_CAP`) and an estimated spend budget of $5 a day (`DAILY_BUDGET_USD`; every model call
is costed by `app/spend.py` from `llm.log_call`, prices `TODO(verify)`).
`CLEARSWATH_LIVE_MODE=off` refuses all of them (503); the cached demo keeps working, an uncached demo is gated too.

`/api/demo?field=&method=&excluded_rules=` (`field` empty, `corrected` or `mt`) serves `data/demo/cache/<field>/inputs.json`
(built by `scripts/build_demo.py`; `mt` by `scripts/build_demo_mt.py`) offline, recomputing the plan each time; without
a cache it runs live (`mt` is cache only). `demo.overlay` is the demo's drone image and its lon/lat bounds, when it has one.

`status` is `go` (nothing removed), `adjust` (some acres removed, the green zone is sprayable; or the label
requires runoff mitigation points, which the user completes in EPA's PALM: a `runoff` rule never changes the map)
or `no-go` (bulletin prohibits, no sprayable area, or `gaps`: data the plan needs is missing, such as a
failed USGS water layer or a buffer rule whose quote couldn't be verified; nothing is sprayable then). It always comes from `buffers.plan`.

Every reason in `plan.reasons` has `source` (`label`, `bulletin`, `rule:water` or `data`); label
reasons also carry `quote`, `page` and `distance_ft`.
