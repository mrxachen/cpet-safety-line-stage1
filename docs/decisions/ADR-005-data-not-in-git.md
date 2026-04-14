# ADR-005: Patient Data Not in Git

**Status**: Accepted
**Date**: 2026-04

## Decision
All real patient data is excluded from version control. Only synthetic demo data
(data/demo/) is committed.

## Implementation
.gitignore excludes data/raw/, data/staging/, data/curated/, data/features/,
data/labels/, data/anchors/, data/contracts/.
