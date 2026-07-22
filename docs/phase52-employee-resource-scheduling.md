# Phase 52.0 — Employee Resource Profiles and Scheduling Priority

This capability separates the number of employees LEOS can define from the
number of employees the current hardware can execute concurrently.

```text
eligible job
  -> admission evaluation
  -> node and model preference selection
  -> atomic capacity reservation
  -> execution
  -> reservation release
```

Profiles can specify minimum CPU, RAM, GPU and VRAM, preferred GPU UUIDs,
provider/model preferences, role priority, concurrency, preemptibility,
execution windows, required node labels, preferred labels, and fallback
resource profiles.

Higher-priority work can receive a preemption plan only when the requester
allows preemption, lower-priority reservations are preemptible, and releasing
them makes the requested workload fit. The plan is committed separately.
