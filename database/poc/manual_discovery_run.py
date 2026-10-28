#!/usr/bin/env python3
"""Additive manual runner: B4 budgets + immutable checkpoints + explicit resume.

CLI is SYNTHETIC FIXTURES ONLY. Library operations/transports remain injected.
No scheduler, database client, deletion, global online collection or key store.
"""

from dataclasses import replace
from datetime import datetime
import argparse
import json
import math
from pathlib import Path
import hmac

from discovery_checkpoints import load_checkpoint, save_checkpoint, _directory
from discovery_execution import execute_source
from discovery_provenance import make_provenance, public_alias, publication_guard, validation_context
from discovery_registry import DEFAULT_MANIFEST, FIXTURE_BINDINGS, discover_fixtures
from execution_models import ExecutionPolicy, ExecutionRuntime, ResourceRef, SourceObservation, SourceTask, Status
from metadata_primitives import copy_metadata, strict_json_loads
from validated_discovery_cache import cache_request, make_cache, validate_cache


FORMAT = "pepeuch-ai.manual-discovery-run/v1"


def timestamp(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("Explicit bounded observation time required")
    date = datetime.fromisoformat(value)
    if date.tzinfo is None:
        raise ValueError("Timezone required")
    return date.timestamp()


def run_manual(tasks, *, runtime, archive, contexts, now, max_age_seconds,
               resume=None, trusted_issuers=None, issuer=None, key=None, on_event=None):
    """Archive each complete source independently before proceeding to the next.

    Resume descriptors contain an EXACT B4 request and immutable checkpoint ID.
    Cached age is an operator policy, not proof of remote freshness or HTTP 304.
    Any invalid descriptor fails before execution; stale descriptors are observed
    again. A callback may persist each event; if interrupted, already published
    checkpoints survive. The caller must explicitly select generations to resume.
    """
    tasks = tuple(replace(t) for t in tasks)
    if not tasks or len({t.source for t in tasks}) != len(tasks):
        raise ValueError("One explicit task per source required")
    if any(not set(t.resources) <= t.policy.resources for t in tasks):
        raise ValueError("Every task resource must be authorized, including cached resumes")
    if any(not t.synthetic for t in tasks):
        public_alias(issuer)
        enrolled = ({} if trusted_issuers is None else trusted_issuers).get(issuer)
        if (not isinstance(key, bytes) or len(key) < 32 or not isinstance(enrolled, bytes)
                or not hmac.compare_digest(key, enrolled)):
            raise ValueError("Controlled operations require an explicitly enrolled issuer before execution")
    if (isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, (int, float))
            or not math.isfinite(max_age_seconds) or not 0 <= max_age_seconds <= 604800):
        raise ValueError("Explicit freshness bound between zero and seven days required")
    epoch = timestamp(now)
    if set(contexts) != {t.source for t in tasks}:
        raise ValueError("Explicit context for every source required")
    contexts = {s: validation_context(c) for s, c in contexts.items()}
    authorize = getattr(trusted_issuers, "authorize", None)
    if authorize is not None:
        for task in tasks:
            if not task.synthetic:
                authorize(issuer, task.source, contexts[task.source], key=key)
    resume = copy_metadata({} if resume is None else resume)
    if not isinstance(resume, dict) or set(resume) - set(contexts):
        raise ValueError("Resume contains unplanned sources")
    # Preflight private anchored storage even if every task would fail/reuse.
    with _directory(archive):
        pass
    cached = {}
    for task in tasks:
        if task.source not in resume:
            continue
        descriptor = resume[task.source]
        if not isinstance(descriptor, dict) or set(descriptor) != {"request", "identity"}:
            raise ValueError("Explicit immutable resume descriptor required")
        entry = load_checkpoint(archive, descriptor["request"], descriptor["identity"], trusted_issuers=trusted_issuers)
        request = entry["request"]
        if (request["source"] != task.source or request["selection"] != task.selection
                or request["resources"] != sorted(r.source_id for r in task.resources)
                or request["context"] != contexts[task.source]
                or (entry["provenance"]["kind"] == "synthetic") != task.synthetic
                or entry["provenance"]["kind"] == "historical_unknown"):
            raise ValueError("Resume scope, provenance or partition differs from the plan")
        age = epoch - timestamp(entry["snapshot"]["captured_at"])
        if age < 0:
            raise ValueError("Future observation cannot establish freshness")
        if age < max_age_seconds:
            cached[task.source] = (entry, age)
    events = []
    for task in tasks:
        source = task.source
        if source in cached:
            entry, age = cached[source]
            # A previous callback can revoke trust after the initial resume
            # preflight. Never publish a cached descriptor using stale approval.
            entry = validate_cache(entry, trusted_issuers=trusted_issuers)
            event = {"source": source, "status": "resumed_cached", "complete": True,
                     "snapshot_id": entry["snapshot"]["snapshot_id"], "captured_at": entry["snapshot"]["captured_at"],
                     "age_seconds": age, "remote_revalidated": False, "resume": resume[source], "execution": None}
        else:
            result = execute_source(task, runtime=runtime)
            event = {"source": source, "status": result.status.value, "complete": result.complete,
                     "snapshot_id": None, "captured_at": None, "age_seconds": None,
                     "remote_revalidated": False, "resume": None, "execution": result.to_manifest()}
            if result.status == Status.SUCCESS:
                snapshot = result.snapshot
                age = epoch - timestamp(snapshot["captured_at"])
                if age < 0:
                    raise ValueError("Future observation refused before checkpoint publication")
                request = cache_request(source, task.selection, [r.source_id for r in task.resources],
                                        context=contexts[source],
                                        revisions={r["source_id"]: r["source_revision"] for r in snapshot["records"]})
                provenance = make_provenance(snapshot, context=contexts[source],
                                             kind="synthetic" if task.synthetic else "controlled_observation",
                                             **({} if task.synthetic else {"issuer": issuer, "key": key}))
                entry = make_cache(request, snapshot, provenance,
                                   validators={"etag": None, "last_modified": None}, trusted_issuers=trusted_issuers)
                identity = save_checkpoint(archive, entry, trusted_issuers=trusted_issuers)
                event.update(snapshot_id=snapshot["snapshot_id"], captured_at=snapshot["captured_at"], age_seconds=age,
                             resume={"request": request, "identity": identity})
        with publication_guard(trusted_issuers):
            if event["complete"]:
                validate_cache(entry, trusted_issuers=trusted_issuers)
                if authorize is not None and not task.synthetic:
                    authorize(issuer, source, contexts[source], key=key)
            events.append(copy_metadata(event))
            if on_event is not None:
                on_event(copy_metadata(event))
    return {"format": FORMAT, "complete": all(e["complete"] for e in events),
            "requested_sources": [t.source for t in tasks], "sources": events,
            "data_kind": "synthetic" if all(t.synthetic for t in tasks) else "controlled_or_mixed",
            "policy": {"now": now, "max_age_seconds": max_age_seconds, "retention": "append_only_no_pruning"},
            "database_imported": False, "remote_freshness_verified": False}


def fixture_tasks(sources, manifest=DEFAULT_MANIFEST):
    """Materialize only local fixtures; each request is explicitly budgeted."""
    sources = tuple(sources)
    if not sources or len(set(sources)) != len(sources) or any(s not in FIXTURE_BINDINGS for s in sources):
        raise ValueError("Distinct registered fixture sources required")
    tasks = []
    for source in sources:
        snapshot = discover_fixtures(manifest, sources=[source])
        refs = tuple(ResourceRef(source, r["source_id"]) for r in snapshot["records"])
        policy = ExecutionPolicy(max_requests=len(refs), max_attempts=1, total_seconds=10, max_delay_seconds=0,
                                 backoff_seconds=0, resources=frozenset(refs), retry_http_statuses=frozenset(), retry_transport_errors=False)
        def operation(context, snapshot=snapshot, refs=refs):
            for ref in refs:
                context.request(ref, lambda remaining: None)
            return SourceObservation(snapshot, True)
        tasks.append(SourceTask(source, snapshot["scope"][source], refs, policy, operation, True, True))
    return tasks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", action="store_true", required=True)
    parser.add_argument("--source", choices=tuple(FIXTURE_BINDINGS), action="append")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--archive-dir", type=Path, required=True, help="Existing private POSIX directory; never auto-created")
    parser.add_argument("--resume", type=Path, help="Explicit source-to-descriptor JSON map from prior events")
    parser.add_argument("--now", required=True, help="Explicit timezone-aware evaluation time")
    parser.add_argument("--max-age-seconds", type=int, required=True)
    args = parser.parse_args()
    try:
        resume = None
        if args.resume:
            with args.resume.open("rb") as stream:
                raw = stream.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ValueError("Bounded resume map required")
            resume = strict_json_loads(raw)
        tasks = fixture_tasks(tuple(FIXTURE_BINDINGS) if args.source is None else args.source, args.manifest)
        contexts = {t.source: {"domain": "fixtures.invalid", "account_partition": "anonymous", "representation": "metadata-v1"} for t in tasks}
        # Fixtures have no I/O waits or retries. Production transport not wired.
        import time
        def no_wait(delay):
            raise ValueError("Fixture execution must not wait")
        runtime = ExecutionRuntime(time.monotonic, time.time, no_wait, lambda delay: 0)
        report = run_manual(tasks, runtime=runtime, archive=args.archive_dir, contexts=contexts,
                            now=args.now, max_age_seconds=args.max_age_seconds, resume=resume,
                            on_event=lambda event: print(json.dumps({"event": event}, sort_keys=True), flush=True))
    except (OSError, ValueError, TypeError, KeyError):
        parser.exit(2, "Manual fixture run refused: invalid plan, cache or archive; prior generations preserved\n")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
