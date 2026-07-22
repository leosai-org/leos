# LEOS Phase 52.4.4 — CLI and Doctor

Phase 52.4.4 introduces the unified `leos` operator command. Inspection is read-only by default. `status`, `doctor`, and `services` inspect governed installation and first-run state. `logs`, `backup`, and `update` create non-executing plans. `install` and `first-run` return explicit handoffs rather than silently mutating the host.

The doctor covers installation, first-run completion, permissions, container and NVIDIA runtime readiness, network exposure, service health, capacity, release integrity, and configuration drift. External network and container-daemon contact remain disabled unless explicitly authorized, and this phase still records no actual contact during acceptance.
