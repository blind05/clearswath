# Module contracts

Shapes are shapely geometries in EPSG:4326 (lon/lat) unless stated. Areas in acres.
Don't change a contract unless the human asks.

| Module | Function | Takes | Returns |
| --- | --- | --- | --- |
| `app/llm.py` | `client()`, `chat()`, `chat_json()`, `data_url()`, `load_prompt()` | messages, JSON schema (object root) | model reply; dict matching schema. Logs every call to `data/logs/calls.jsonl` |
| `app/geo.py` | `load_field()`, `save_shapes()`, `load_shapes()`, `to_feature_collection()` | GeoJSON paths, shapes | shapely shapes in EPSG:4326; GeoJSON dicts |
| `app/imagery.py` | `fetch_tile(field_path, out_png)` | field GeoJSON | PNG plus `.json` sidecar: crs, transform (6 values, downscaled), date, width, height |
| `app/imagery.py` | `usgs_water(field_path)` | field GeoJSON, optional `failed` list | list of water shapes; names of layers that errored are appended to `failed` |
| `app/segment.py` | `find_hazards(field_path)` | field GeoJSON | `{water, building, habitat, imagery_date, water_source, water_warnings}`; cached per field and hazard |
| `app/label_reader.py` | `read_label(path)` | PDF or image | `LabelRules`: product_name, epa_reg_no, rules (kind, target, applies_to, value, unit, summary, quote, page), dropped, source |
| `app/bulletins.py` | `check_bulletin(field_path, month, reg_no)` | field, month, product | `{in_pula, prohibited, limitations, restricted, citation, checked}` |
| `app/buffers.py` | `plan(field, hazards, rules, restricted, method, prohibited)` | shapes and rules | `{status, method, field_acres, spray_acres, excluded_acres, spray_zone, no_spray, reasons}` |
| `app/pipeline.py` | `run(field_path, label_path, month, method)`, `to_json(result)` | paths and options | full result; JSON with map layers for the page |
| `app/agent.py` | `run(field_path, label_path, month, method)` | same | `{run_id, answer, decision, trace, mode, result}`; `result` is what `pipeline.run` returns |
| `app/records.py` | `transcribe(path)`, `fill_record(text, job)` | audio; transcript and job dict | text; `AppRecord` with `missing` list |
| `app/api.py` | `/api/demo`, `/api/label`, `/api/plan`, `/api/agent`, `/api/kml/{id}`, `/api/record` | form uploads | JSON for `web/index.html` |

`status` is `go` (nothing removed), `adjust` (some acres removed; the green zone is sprayable)
or `no-go` (bulletin prohibits, or no sprayable area). It always comes from `buffers.plan`.

Every reason in `plan.reasons` has `source` (`label`, `bulletin` or `rule:water`); label
reasons also carry `quote`, `page` and `distance_ft`.
