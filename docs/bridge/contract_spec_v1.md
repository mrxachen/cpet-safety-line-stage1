# Contract Specification v1

## Subject ID Contract

Format: `S{YYYY}{NNNN}` (e.g., S20230001)
- Immutable once assigned
- Unique across all stages

## Session ID Contract

Format: `{subject_id}_{YYYYMMDD}` (e.g., S20230001_20230415)
- One record per CPET session per subject
- Multiple sessions per subject allowed (grouped in CV splits)

## Stage Linking

To link Stage I anchors to Stage II proxies:
1. Export anchor package from `make anchors`
2. Include `subject_id`, `session_id`, and all R/T/I axis fields
3. Format: Parquet (schema v1)
4. Required fields: vt1_hr, rcp_hr, vo2_peak_pct_pred, eih_status, p1_zone

See `configs/bridge/contract_rules_v1.yaml`.
