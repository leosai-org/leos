# LEOS Employee Registry

The employee registry is the canonical Phase 52.2 authority for employee definitions, lifecycle state, execution eligibility, assignment policy, resource-profile synchronization, and revision history.

The service migrates the legacy `employees.json` registry into SQLite once, preserves legacy registration routes, and exposes the v2 employee lifecycle API documented in `docs/phase52.2-employee-definition-lifecycle.md`.
