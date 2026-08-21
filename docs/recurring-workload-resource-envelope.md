# Recurring Workload Resource Envelope Evidence

Ticket / Spec: `RUNTIME-RESOURCE-ENVELOPE-EVIDENCE-001`

Chzzk terminal correlation amendment:
`RUNTIME-RESOURCE-ENVELOPE-CHZZK-TERMINAL-CORRELATION-001`

This is a local/private, read-only evidence contract for the current recurring
PMTS workloads. It does not select a cloud provider or VM size, change a
scheduler, start a workload, modify an existing result artifact, or write to a
database.

## Workload discovery and correlation

The observer recognizes only these normalized identities:

| Workload ID | Existing entrypoint/result contract |
| --- | --- |
| `steam.ccu-30m` | `steam.ingest.run_steam_cadence_job ccu-30m` and Steam cadence `result.json` |
| `steam.price-1h` | `steam.ingest.run_steam_cadence_job price-1h` and Steam cadence `result.json` |
| `steam.daily` | `steam.ingest.run_steam_cadence_job daily` and Steam cadence `result.json` |
| `chzzk.fetch-load-guarded-write-30m` | guarded-write wrapper, wrapper trace, and guarded-write or narrowly validated early-terminal result |

Root discovery reads cmdline at most once per 250ms discovery interval and only for
processes whose short Linux process name is an expected shell, Poetry, or
Python candidate. It never reads `/proc/<pid>/environ`, never persists cmdline,
and uses only stat/status, PPID, and `(pid, starttime_ticks)` identity while an
already discovered process tree is active.

`origin_assertion: process_signature_only` is intentional: process evidence
does not itself prove that a Windows scheduler triggered the command.

Steam correlation requires one result with the matching cadence whose existing
start/end UTC interval overlaps the observed process interval within two
seconds. Chzzk correlation matches the wrapper PID internally against the
sanitized wrapper start marker. A valid `guarded-write-result.json` is the
primary result and records `existing_result_phase: guarded_write`. The observer
considers `no-write-result.json` only when the guarded result is missing, and
only status `hard_failure` is a supported early-terminal outcome. That outcome
requires canonical producer binding, a matching readable wrapper end marker,
and a valid nonzero wrapper exit; it records
`existing_result_phase: no_write_terminal`. This phase distinguishes a
pre-guard terminal outcome from guarded execution without reclassifying the
producer's result status.

If a guarded result exists but is malformed, unreadable, or invalid, the
observer does not fall back to no-write evidence. Missing, malformed, invalid,
or ambiguous no-write/end evidence also fails closed as unreadable and does not
imply a terminal outcome. A Chzzk successful guarded result with a nonzero
wrapper exit remains a conflict, not a newly invented success or failure status.

Persisted Steam and Chzzk run IDs must match the recurring producers' canonical
`%Y%m%dT%H%M%S%fZ` UTC form. Chzzk wrapper boundary IDs must match the wrapper's
canonical `%Y%m%dT%H%M%SZ` form and agree with the start/end marker boundary.
Invalid identifiers fail closed as unreadable and their raw values are never
persisted. Existing statuses, including Chzzk `lock_busy`, are preserved without
reclassification.

Artifact-only Chzzk fallback reuses the same guarded-primary and narrow
early-terminal validation contracts and requires matching end evidence. Because
no process PID was observed, its correlation state remains `unmatched`; the run
is retained only as `process_not_observed` incomplete evidence and is not
presented as a process match. Normalized producer status and result phase may be
preserved, but artifact-only evidence never creates a process correlation.

## Resource semantics

`peak_aggregate_rss_bytes` means **maximum sampled sum of process-tree
`VmRSS`**. It includes the discovered root and its concurrently attached Linux
descendants, such as shell, Poetry, Python, and helper processes. It excludes
PostgreSQL, Windows `wsl.exe`, kernel page cache, and unrelated host processes.

Three caveats remain separate:

- `temporal_peak_may_be_missed`: periodic polling can miss an instantaneous
  process-tree peak.
- `shared_pages_may_be_double_counted`: summing per-process RSS can count shared
  mappings more than once.
- `vmrss_accounting_may_be_approximate`: Linux `VmRSS` accounting itself is
  approximate for this use.

The metric is therefore not described as a physical-RAM lower or upper bound.
This ticket deliberately does not poll `smaps` or `smaps_rollup`.

CPU uses the Linux host's runtime `SC_CLK_TCK`, never a hardcoded tick rate.
For a stable process-tree snapshot, each live node contributes its own
`utime/stime` plus CPU of its already waited-for children in `cutime/cstime`.
Before accepting a sample, the observer verifies that tree membership and each
reachable parent's child-time counters stayed stable over the read. A child
exit/reap transition can otherwise double-count or omit CPU in a non-atomic
`/proc` view. Unstable snapshots are discarded rather than estimated. Each
sampling cycle makes one initial read plus at most two immediate additional
retries after a handoff instability; this fixed bound limits observer work
within the 100ms target budget.

The CPU counters have distinct meanings: `handoff_retry_count` counts only
additional attempts actually made after an unstable handoff read;
`handoff_unstable_snapshot_count` counts discarded raw attempts with a tree or
child-time transition; `invalid_snapshot_count` counts sampling cycles with no
accepted snapshot after that bounded retry. A recovered retry remains a valid
sample and does not by itself make evidence partial. Retry exhaustion records
`cpu_handoff_snapshot_unstable`; CPU is never estimated or interpolated.

When a per-process stat/status sample fails, the observer re-reads the tree
inventory before classifying it. A disappeared process, changed membership, or
changed `(pid, starttime_ticks)` identity follows the bounded handoff retry
path. If inventory and identity remain unchanged, the cycle fails closed with
`proc_snapshot_unavailable`, including when an earlier attempt in that cycle
already triggered a handoff retry.

Elapsed duration, sample gap, lifecycle tolerance, and overlap duration use
Linux `CLOCK_BOOTTIME`. Persisted UTC timestamps are human-readable context and
existing-artifact correlation only.

## Sampling and completeness

The target interval is 100ms; it is not a guaranteed interval. The observer
records actual gaps between completed valid snapshots and uses:

```text
gap_threshold_ms = max(250ms, 2 * target_interval_ms)
total_sample_gap_excess_ms =
    sum(max(0, observed_gap_ms - gap_threshold_ms))
```

Any threshold-exceeding gap prevents `complete` and adds
`sampling_gap_exceeded`. `complete` means `no_known_observation_contract_gap`,
not a kernel-exact resource peak.

`observed_overlap_lower_bound_ms` includes only the monotonic intersection of
two runs' intervals between consecutive valid samples, when neither valid-sample
gap exceeds the threshold. The active-process registry alone is not overlap
evidence: exited, identity-mismatched, missing, or invalid current samples do
not update `observed`, `workload_ids`, `peak_other_run_count`, `sample_count`,
or overlap timestamps. The overlap scope is limited to the four recognized PMTS
workloads.

## Private output and smoke usage

Evidence is written atomically below:

```text
tmp/observability/resource-envelope/<session-id>/
```

Directories use mode `0700` and JSON files use mode `0600`. Summaries contain
only normalized workload IDs, bounded existing run/boundary IDs, timestamps,
numeric measurement fields, completeness, overlap, and sanitized correlation
fields. They never contain command lines, environment variables, credentials,
host identity, paths, raw result artifacts, or exception text.

Use a bounded foreground session near a naturally scheduled run. For harmless
manual validation only, explicit PID mode accepts `synthetic.smoke`; it does not
start or wrap a target workload. An absence of natural observed runs is a valid
session outcome and must not trigger a manual Steam or Chzzk job run.

Actual natural-run accumulation and VM sizing interpretation are separate
operational follow-up work.
