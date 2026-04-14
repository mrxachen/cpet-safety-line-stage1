# ADR-001: P0 Proxy Label Strategy

**Status**: Accepted
**Date**: 2026-04

## Context
No prospective follow-up data exists. We need a binary safety outcome for P0.

## Decision
Use CPET test-time adverse events as proxy labels (arrhythmia, EIH, early termination).

## Consequences
- Leakage risk: these flags must be excluded from P0 features (see leakage_guard.py)
- Labels reflect "test reactivity", not long-term cardiovascular risk
- Model generalizes to supervised exercise settings, not community walking
