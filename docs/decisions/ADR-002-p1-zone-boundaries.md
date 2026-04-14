# ADR-002: P1 Zone Boundary Definitions

**Status**: Accepted
**Date**: 2026-04

## Decision
Green/Yellow/Red boundaries based on:
- VO2peak %predicted: <50 (red), 50-70 (yellow), ≥70 (green)
- VE/VCO2 slope: >36 (red), 30-36 (yellow), ≤30 (green)
- EIH: true → red

Conflict resolution: take_worst.

## Rationale
AHA/ACSM exercise prescription literature; aligns with cardiac rehab intensity zones.
