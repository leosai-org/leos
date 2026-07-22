# LEOS Phase 52.4.3 — First-Run Experience

Phase 52.4.3 adds a deterministic, resume-safe first-run state machine on top
of the Phase 52.4.2 installer.

## Operator flow

1. Complete the governed installation transaction.
2. Run `leos-first-run plan` against the installed target.
3. Review the generated session ID, administrator bootstrap, node plan,
   runtime selection, and readiness report.
4. Run `leos-first-run apply --confirm <session-id>`.
5. Activate the administrator credential through a later authenticated
   control-plane operation. No plaintext credential is written by first-run.

The first-run apply writes six files beneath the installation target. Repeating
the same operation is idempotent. Missing or drifted first-run files are
repaired. A write failure restores the previous state.

External providers require explicit network permission, but Phase 52.4.3 does
not contact external networks or a container daemon. Service deployment and
credential activation remain deferred.
