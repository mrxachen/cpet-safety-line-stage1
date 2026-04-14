# Anchor Variable Dictionary v1

Three-axis anchor framework for Stage I → Stage II bridge.

## Axis R: Functional Reserve

| Variable | Field | Unit | Priority | Home Proxy |
|---|---|---|---|---|
| R1 | vo2_peak_pct_pred | % | Critical | 6MWT %predicted |
| R2 | o2_pulse_peak | mL/beat | High | Resting HRV RMSSD |
| R3 | vt1_pct_vo2peak | % | High | Talk test threshold HR |

## Axis T: Exercise Threshold

| Variable | Field | Unit | Priority | Home Proxy |
|---|---|---|---|---|
| T1 | vt1_hr | bpm | Critical | Target HR zone for home exercise |
| T2 | rcp_hr | bpm | High | RPE 14-15 at this HR |
| T3 | vt1_load_w | W | Medium | Cycle cadence proxy |
| T4 | ve_vco2_slope | — | High | Breathing frequency proxy |

## Axis I: Instability Indicators

| Variable | Field | Unit | Priority | Home Proxy |
|---|---|---|---|---|
| I1 | eih_status | bool | Critical | Pulse oximeter required |
| I2 | eih_nadir_spo2 | % | High | SpO2 at target HR |
| I3 | bp_response_abnormal | bool | Medium | Wrist BP monitoring |
| I4 | arrhythmia_flag | bool | High | Single-lead ECG band |

See `configs/bridge/anchor_rules_v1.yaml` for full definitions.
