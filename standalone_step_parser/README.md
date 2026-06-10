# Standalone STEP Parser

Independent STEP geometry parser for downstream process recognition and pricing.
It does not modify the existing pricing core and can be run as a separate tool.

## What It Extracts

- Bounding box: length, width, height in `mm`
- Volume: `mm3`
- Surface area: `mm2`
- Optional net weight when material density is provided
- Part type candidates: `thin_plate`, `plate`, `block`, `shaft`, `complex`, `small_irregular`
- Hole candidates from cylindrical faces
- Profile summary for plate-like parts, including estimated top profile length
- Outer profile, inner profile, and slot-like inner profile candidates
- Shaft/turned-part candidates from round cross sections, cylindrical face ratio,
  and circular edge ratio
- Short turned/flange-like candidates from cylindrical area ratio, circular edge
  ratio, and freeform BSPLINE turned-surface signals
- Complexity metrics: face count, edge count, small radius count, thin-wall candidate, score
- Geometry risks such as high-risk geometry or parser failure

## Install

Use a normal Python virtual environment and install CadQuery with pip.
The parser still has a pythonocc backend in code, but Windows pip installs are
usually much easier with CadQuery, so CadQuery is the recommended no-conda path.

PowerShell:

```powershell
python -m venv .venv-step-parser
.\.venv-step-parser\Scripts\python.exe -m pip install --upgrade pip
.\.venv-step-parser\Scripts\python.exe -m pip install -r standalone_step_parser\requirements.txt
```

If your environment already has one backend, the parser can run with that backend:

```powershell
.\.venv-step-parser\Scripts\python.exe standalone_step_parser\cli.py sample.step --backend cadquery
```

Run the real STEP read test:

```powershell
$env:STEP_PARSER_BACKEND="cadquery"
.\.venv-step-parser\Scripts\python.exe -m unittest standalone_step_parser.tests.test_real_step_read -v
```

## Usage

Generate `step_feature_result`:

```powershell
.\.venv-step-parser\Scripts\python.exe standalone_step_parser\cli.py input.step `
  --task-id task_001 `
  --file-id file_step_001 `
  --density 0.00000785 `
  --density-unit kg/mm3 `
  --output tmp/step_feature_result.json
```

Generate both `step_feature_result` and an A-side `part_feature` stub:

```powershell
.\.venv-step-parser\Scripts\python.exe standalone_step_parser\cli.py input.step `
  --task-id task_001 `
  --file-id file_step_001 `
  --density 0.00000785 `
  --material-code SKD11 `
  --material-name SKD11 `
  --output tmp/step_feature_result.json `
  --part-feature-output tmp/part_feature_from_step.json
```

The `part_feature` stub is meant for A-side trial pricing only. PDF-derived
fields such as heat treatment, surface treatment, precision tolerance, drawing
number, and packaging notes should still come from PDF parsing or manual review.

## Output Shape

The primary output is a STEP-specific payload:

```json
{
  "schema_version": "1.0",
  "task_id": "task_001",
  "file_id": "file_step_001",
  "backend": "cadquery",
  "bounding_box": {"length": 120.0, "width": 80.0, "height": 12.0, "unit": "mm"},
  "volume": {"value": 82000.0, "unit": "mm3", "source": {"source_type": "step", "file_id": "file_step_001"}},
  "surface_area": {"value": 24500.0, "unit": "mm2", "source": {"source_type": "step", "file_id": "file_step_001"}},
  "net_weight": {"value": 0.6437, "unit": "kg", "density": 0.00000785, "density_unit": "kg/mm3"},
  "part_type_candidates": [],
  "holes": [],
  "hole_summary": {
    "total_count": 111,
    "by_type": {"through": 111},
    "by_diameter": {"5.0": 26, "6.0": 10, "6.8": 32, "18.0": 17}
  },
  "hole_groups": [
    {
      "group_id": "hole_group_1",
      "diameter": 6.8,
      "count": 8,
      "array_type": "grid_array",
      "x_count": 4,
      "y_count": 2,
      "x_spacing_candidates": [35.0],
      "y_spacing_candidates": [45.0]
    }
  ],
  "counterbore_candidates": [
    {
      "base_diameter": 11.0,
      "counterbore_diameter": 18.0,
      "counterbore_depth": 10.6,
      "count": 17,
      "confidence": 0.72
    }
  ],
  "slot_candidates": [
    {
      "slot_type": "elongated_slot",
      "count": 3,
      "confidence": 0.68,
      "avg_profile_length": 2338.8319,
      "max_profile_length": 2338.8319,
      "avg_length": 968.0,
      "avg_width": 210.0,
      "avg_line_length": 2276.0,
      "avg_arc_length": 62.8319
    }
  ],
  "profile_summary": {
    "outer_profile_length": 5993.2687,
    "outer_line_length": 5961.8528,
    "outer_arc_length": 31.4159,
    "outer_line_count": 14,
    "outer_arc_count": 2,
    "inner_profile_length": 7885.5836,
    "inner_line_length": 2876.0,
    "inner_arc_length": 5009.5844,
    "inner_line_count": 12,
    "inner_arc_count": 234,
    "total_edge_length": 34172.6604,
    "top_profile_length": 13878.8524,
    "inner_profile_count": 114,
    "circular_inner_profile_count": 111,
    "slot_candidate_count": 3,
    "line_edge_length": 22915.7056,
    "circular_edge_length": 11256.9548,
    "circular_edge_count": 540
  },
  "complexity": {},
  "geometry_risks": []
}
```

## Notes

- Hole detection is a geometry candidate extractor, not a final manufacturing
  decision. Cylindrical faces can also come from shafts, bosses, or fillets.
- Thread, counterbore, countersink, and precision-hole decisions usually need
  PDF annotations or manual review.
- Hole groups are heuristic clusters by diameter and position. Use them for
  quoting explanation and batch-operation hints, not as a strict drawing truth.
- Shaft detection is geometry-only. It identifies shaft/turned-part candidates,
  but PDF names or process labels are still needed to distinguish welding,
  turning, and secondary machining requirements.
- This module must not calculate prices directly; it only prepares geometry
  features for process recognition and engineering quantity calculation.
