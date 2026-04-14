# ADR-003: Group-Based CV Split

**Status**: Accepted
**Date**: 2026-04

## Decision
Use subject_id as group key in KFold splits to prevent data leakage from multiple sessions.

## Consequence
Effective sample size = number of unique subjects, not total sessions.
