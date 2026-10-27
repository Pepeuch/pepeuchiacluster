"""B4.4 sequential execution/retries, explicitly separate from HTTP and CLI.

Operations, clocks, waiting and jitter are injected. No default real transport,
clock, sleep, scheduler, persistence or database connection is constructed here.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from http.client import IncompleteRead
from json import JSONDecodeError
import math
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError

from execution_models import (
    ExecutionError, ExecutionPolicy, ExecutionReport, ExecutionRuntime, Reason,
    ResourceRef, SourceObservation, SourceResult, SourceTask, Status, number, validate_observation,
)
from metadata_http import MetadataHTTPError, MetadataNetworkError, MetadataResponseError
from retry_after import RetryAfter, parse_retry_after


@dataclass(frozen=True)
class ClassifiedError:
    reason: Reason
    retryable: bool
    retry_after: RetryAfter | None = None


def classify_error(exc: Exception, *, source: str, policy: ExecutionPolicy) -> ClassifiedError:
    """Classify by type/status only. Never parse exception text or HTTP bodies."""
    if isinstance(exc, ExecutionError):
        return ClassifiedError(exc.reason, False)
    if isinstance(exc, HTTPError):
        code = exc.code
        if type(code) is not int or not 100 <= code <= 599:
            return ClassifiedError(Reason.INVALID_SCHEMA, False)
        reason = {
            401: Reason.AUTHENTICATION, 403: Reason.FORBIDDEN,
            404: Reason.NIM_TAG_UNAVAILABLE if source == "nvidia-nim-metadata" else Reason.TARGET_UNAVAILABLE,
            429: Reason.QUOTA, 304: Reason.CACHE_REQUIRED,
        }.get(code, Reason.PROVIDER if code in (500, 502, 503, 504) else
              Reason.REDIRECT if type(code) is int and 300 <= code < 400 else Reason.HTTP_ERROR)
        try:
            # Compatibility seam for an explicitly injected legacy HTTPError:
            # inspect only this field, never retain/expose the header collection.
            retry_after = (exc.retry_after if isinstance(exc, MetadataHTTPError) else
                           parse_retry_after(exc.headers.get("Retry-After")) if exc.headers is not None else None)
        except Exception:
            return ClassifiedError(Reason.INVALID_SCHEMA, False)
        if retry_after is not None and not isinstance(retry_after, RetryAfter):
            return ClassifiedError(Reason.INVALID_SCHEMA, False)
        return ClassifiedError(reason, code in policy.retry_http_statuses, retry_after)
    if isinstance(exc, TimeoutError) or (isinstance(exc, URLError) and isinstance(exc.reason, TimeoutError)):
        return ClassifiedError(Reason.TIMEOUT, policy.retry_transport_errors)
    if isinstance(exc, (MetadataNetworkError, ConnectionError, IncompleteRead, URLError)):
        return ClassifiedError(Reason.CONNECTION, policy.retry_transport_errors)
    if isinstance(exc, (MetadataResponseError, JSONDecodeError, UnicodeError)):
        return ClassifiedError(Reason.INVALID_JSON, False)
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return ClassifiedError(Reason.INVALID_SCHEMA, False)
    return ClassifiedError(Reason.UNEXPECTED, False)


class _Budget:
    def __init__(self, policy: ExecutionPolicy, runtime: ExecutionRuntime):
        self.policy, self.runtime = policy, runtime
        self.attempts = self.requests = 0
        self.elapsed = self.waited = 0.0
        self.start = self.last = self._clock()

    def _clock(self) -> float:
        try:
            value = self.runtime.monotonic()
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError()
            return float(value)
        except Exception:
            raise ExecutionError(Reason.RUNTIME) from None

    def sample(self) -> float:
        now = self._clock()
        if now < self.last or not math.isfinite(now - self.start):
            raise ExecutionError(Reason.RUNTIME)
        self.last, self.elapsed = now, now - self.start
        return max(0.0, self.policy.total_seconds - self.elapsed)

    def check_time(self) -> float:
        remaining = self.sample()
        if remaining <= 0:
            raise ExecutionError(Reason.TIME_BUDGET)
        return remaining


class AttemptContext:
    """All individual metadata dispatches must go through request().

    Callback receives the remaining total seconds; it must cap its own socket
    timeout accordingly. The executor cannot preempt a blocking callback or
    count hidden HTTP calls inside an opaque SDK.
    """

    def __init__(self, task: SourceTask, budget: _Budget):
        self._task, self._budget, self._active = task, budget, True

    def close(self) -> None:
        self._active = False

    def request(self, resource: ResourceRef, callback: Callable[[float], Any]) -> Any:
        if (not self._active or resource not in self._task.resources
                or resource not in self._task.policy.resources):
            raise ExecutionError(Reason.SELECTION)
        remaining = self._budget.check_time()
        if self._budget.requests >= self._task.policy.max_requests:
            raise ExecutionError(Reason.REQUEST_BUDGET)
        self._budget.requests += 1
        result = callback(remaining)
        self._budget.check_time()
        return result


def _backoff(policy: ExecutionPolicy, attempt: int) -> float:
    # Saturation avoids huge powers/overflow, including enormous attempt limits.
    delay = policy.backoff_seconds
    for _ in range(attempt - 1):
        if delay == 0 or delay >= policy.max_delay_seconds / 2:
            return 0.0 if delay == 0 else policy.max_delay_seconds
        delay *= 2
    return min(delay, policy.max_delay_seconds)


def _server_delay(info: RetryAfter | None, runtime: ExecutionRuntime) -> float | int:
    if info is None:
        return 0.0
    if info.excessive:
        raise ExecutionError(Reason.RETRY_AFTER_EXTREME)
    if info.seconds is not None:
        return info.seconds
    try:
        now = runtime.wall_time()
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now):
            raise ValueError()
        target = info.not_before
        if info.legacy_date is not None:
            yy, month, day, hour, minute, second, weekday = info.legacy_date
            current = datetime.fromtimestamp(now, timezone.utc)
            try:
                date = datetime(current.year // 100 * 100 + yy, month, day, hour, minute, second, tzinfo=timezone.utc)
                if current.year <= 9949:
                    try:
                        cutoff = current.replace(year=current.year + 50)
                    except ValueError:
                        cutoff = current.replace(year=current.year + 50, day=28)
                    if date > cutoff:
                        date = date.replace(year=date.year - 100)
                if date.weekday() != weekday:
                    return 0.0  # Invalid date, use the local backoff only.
                target = date.timestamp()
            except ValueError:
                return 0.0
        delay = max(0.0, target - now)
        if not math.isfinite(delay):
            raise ValueError()
        return delay
    except Exception:
        raise ExecutionError(Reason.RUNTIME) from None


def execute_source(task: SourceTask, *, runtime: ExecutionRuntime) -> SourceResult:
    """Run a complete planned selection; never expose a failed/partial snapshot."""
    if not isinstance(task, SourceTask) or not isinstance(runtime, ExecutionRuntime):
        raise ValueError("Explicit task and runtime required")
    # Own the plan; a callback mutating the caller's dictionaries cannot change
    # the scope against which its result will be checked.
    task = replace(task)
    budget = None
    last_error = None

    def finish(status, reason=None, snapshot=None):
        result = SourceResult(
            task.source, task.selection, task.resources, status, reason, last_error,
            0 if budget is None else budget.attempts, 0 if budget is None else budget.requests,
            0.0 if budget is None else budget.elapsed, 0.0 if budget is None else budget.waited,
            task.policy, task.idempotent, task.synthetic, status in (Status.SUCCESS, Status.UNCHANGED), snapshot,
        )
        if status in (Status.SUCCESS, Status.UNCHANGED):
            # Result construction validates/copies the snapshot too. Include
            # that work before publication, without rebuilding/validating again.
            budget.check_time()
            object.__setattr__(result, "elapsed_seconds", budget.elapsed)
        return result

    try:
        budget = _Budget(task.policy, runtime)
        if not set(task.resources) <= task.policy.resources:
            return finish(Status.FAILED, Reason.SELECTION)
        while budget.attempts < task.policy.max_attempts:
            budget.check_time()
            budget.attempts += 1
            context = AttemptContext(task, budget)
            try:
                observation = task.operation(context)
                if not isinstance(observation, SourceObservation) or type(observation.complete) is not bool:
                    raise ExecutionError(Reason.INVALID_SCHEMA)
                if not observation.complete:
                    raise ExecutionError(Reason.INCOMPLETE)
                snapshot = validate_observation(task.source, task.selection, task.resources, observation.snapshot)
                budget.check_time()
            except Exception as exc:
                error = classify_error(exc, source=task.source, policy=task.policy)
            else:
                return finish(Status.SUCCESS, snapshot=snapshot)
            finally:
                context.close()
            last_error = error.reason
            remaining = budget.sample()
            if error.reason in (Reason.REQUEST_BUDGET, Reason.TIME_BUDGET):
                return finish(Status.DEFERRED, error.reason)
            if not error.retryable or not task.idempotent:
                return finish(Status.FAILED, error.reason)
            if remaining <= 0:
                return finish(Status.DEFERRED, Reason.TIME_BUDGET)
            if budget.requests >= task.policy.max_requests:
                return finish(Status.DEFERRED, Reason.REQUEST_BUDGET)
            if budget.attempts >= task.policy.max_attempts:
                return finish(Status.DEFERRED, Reason.ATTEMPT_BUDGET)
            server_delay = _server_delay(error.retry_after, runtime)
            if server_delay >= remaining:
                return finish(Status.DEFERRED, Reason.RETRY_AFTER_BUDGET)
            if server_delay > task.policy.max_delay_seconds:
                return finish(Status.DEFERRED, Reason.DELAY_LIMIT)
            base = _backoff(task.policy, budget.attempts)
            try:
                jitter = number(runtime.jitter(base))
            except Exception:
                raise ExecutionError(Reason.RUNTIME) from None
            remaining = budget.check_time()  # Include clock/jitter planning cost.
            if server_delay >= remaining:
                return finish(Status.DEFERRED, Reason.RETRY_AFTER_BUDGET)
            delay = max(server_delay, base + min(jitter, task.policy.max_delay_seconds - base))
            if delay >= remaining:
                return finish(Status.DEFERRED, Reason.TIME_BUDGET)
            before = budget.last
            if delay:
                try:
                    runtime.sleep(delay)
                except Exception:
                    budget.sample()
                    budget.waited += budget.last - before
                    raise ExecutionError(Reason.RUNTIME) from None
            remaining = budget.sample()
            if delay:
                budget.waited += budget.last - before
            if remaining <= 0:
                return finish(Status.DEFERRED, Reason.TIME_BUDGET)
            if budget.last - before < delay:
                return finish(Status.DEFERRED, Reason.WAIT_INTERRUPTED)
        return finish(Status.DEFERRED, Reason.ATTEMPT_BUDGET)
    except ExecutionError as exc:
        if budget is not None and exc.reason != Reason.TIME_BUDGET:
            try:
                budget.sample()
            except ExecutionError:
                pass  # Preserve the last valid measurement if the clock fails.
        return finish(Status.DEFERRED if exc.reason in (
            Reason.TIME_BUDGET, Reason.RETRY_AFTER_EXTREME,
        ) else Status.FAILED, exc.reason)


def execute_sources(tasks: Iterable[SourceTask], *, runtime: ExecutionRuntime) -> ExecutionReport:
    """Sequential per-source budgets; no aggregate B2 snapshot on partial success."""
    tasks = tuple(tasks)
    if not tasks or any(not isinstance(task, SourceTask) for task in tasks) or len({t.source for t in tasks}) != len(tasks):
        raise ValueError("One explicit task per requested source required")
    # Freeze the whole plan before any source callback can mutate a caller's
    # still-mutable selection dictionary belonging to a later source.
    tasks = tuple(replace(task) for task in tasks)
    return ExecutionReport(tuple(execute_source(task, runtime=runtime) for task in tasks))
