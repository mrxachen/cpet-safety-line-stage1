# Data Request Checklist

Use this checklist when preparing data requests to the hospital data center.

## Required Fields (P0 model)

- [ ] Subject anonymized ID
- [ ] Age at test
- [ ] Sex
- [ ] Height, Weight, BMI
- [ ] Diagnosis (HTN / CAD / HF flags)
- [ ] LVEF (if available)
- [ ] NYHA class
- [ ] Resting BP (SBP/DBP)
- [ ] Resting HR
- [ ] VO2peak (mL/kg/min)
- [ ] VO2peak %predicted
- [ ] HR_peak, HR_peak %predicted
- [ ] Peak work rate (W)
- [ ] Peak RER
- [ ] O2 pulse peak
- [ ] VE/VCO2 slope
- [ ] Test termination flag + reason

## Required Fields (P1 model — additional)

- [ ] VT1: VO2, HR, load, %VO2peak
- [ ] RCP/VT2: VO2, HR, load, %VO2peak
- [ ] EIH status + nadir SpO2
- [ ] Abnormal BP response flag
- [ ] ST depression (mm)
- [ ] Arrhythmia flag

## Optional / Nice-to-Have

- [ ] Medications (beta-blocker, ACEi/ARB, diuretics)
- [ ] 6MWT distance (if performed within ±3 months)
- [ ] BNP/NT-proBNP (for HF subgroup)
- [ ] Resting ECG findings

## Data Format Requirements

- Excel or CSV format
- One row per CPET session
- Chinese column headers acceptable (will be mapped via field_map_v1.yaml)
- Date format: YYYY-MM-DD preferred
