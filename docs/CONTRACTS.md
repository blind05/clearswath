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
| `app/api.py` | `/api/demo`, `/api/demo/image/{name}`, `/api/label`, `/api/plan`, `/api/agent`, `/api/kml/{id}`, `/api/export/{id}/{dji,geojson}`, `/api/record`, `/api/photo` | form uploads | JSON for `web/index.html` |

Drift rules (engine rule 2) buffer the treated area toward unmanaged land: everything outside the field that
the user hasn't marked as managed (`hazards["managed"]`), in every direction, or downwind only when a wind
direction is given (`wind_from`, compass degrees, on `/api/plan`, `/api/agent` and `/api/demo`; managed land as
a GeoJSON `managed` form field, checked by `geo.load_managed`: polygons within ~2 km of the field, at most 50).
Unmanaged gaps under 0.5 m are ignored as drawing noise. A drift or buffer rule whose quote
fails the check is a `gap` (NO-GO).

Every label rule is applied. Buffer rules with a `condition` (e.g. "ULV aerial only"), and every rule
read from a photo, are listed in `confirm`; the user can untick them (`excluded_rules`, ids = indexes into
`label.rules`). Unticking anything else is refused. A model's condition can only make the plan stricter.

Paid endpoints (`/api/plan`, `/api/agent`, `/api/label`, `/api/record`, `/api/photo`) need the `X-Access-Code` header when
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
failed USGS water layer, a buffer rule whose quote couldn't be verified, or a label read that returned no rules at
all; nothing is sprayable then). It always comes from `buffers.plan`.

Every reason in `plan.reasons` has `source` (`label`, `bulletin`, `rule:water` or `data`); label
reasons also carry `quote`, `page` and `distance_ft`.

Live photo mode: `/api/photo` takes one JPEG, PNG or WebP (re-encoded upright, EXIF dropped, at most 3000 px) and
`llm.weed_photo` posts it to the Modal endpoint in `serve/weeds_modal.py` (`PHOTO_URL`, with `PHOTO_KEY` sent as
`X-Photo-Key`). The endpoint runs DINOv3 and the head from `train/deploy_head_modal.py` (CoFly-WeedDB + PhenoBench)
and returns an RGBA overlay PNG, the share flagged and what the head was trained on. A scouting guide, not a spray map.

Spray volume: `carrier` rules (a minimum total spray volume, gal/acre or L/ha) give `pipeline.carrier_minimum`, the
largest minimum on the label for the method in L/ha, saved in `job.json` and shown on the page. `/api/export/{id}/dji`
refuses a rate below it (422, with the quote), and refuses (409) when a carrier rule on the label failed its checks.
