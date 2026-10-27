"""B4.3 design prototype: static source descriptions, no collectors/loaders.

Not wired to any CLI. Does not import adapters, optional SDKs or plugins, open
connections, compute B2 identities, or decide admission to a personal catalog.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from types import MappingProxyType
from typing import Iterable, Mapping


RESOURCE_TYPES = frozenset({
    "model_reference", "model_artifact", "agent_resource", "nim_microservice", "inference_endpoint",
})
SELECTION_MODES = frozenset({"first_n_sorted", "exact_ids", "first_n_unique", "exact_tag"})
CAPABILITIES = frozenset({
    "metadata", "offline_fixture", "local_pinning", "catalog_pinning",
    "explicit_model_relationships", "file_listing", "observed_formats",
    "deployment_profiles", "served_model_listing",
})


@dataclass(frozen=True)
class TransportSpec:
    kind: str
    configured_hosts: frozenset[str]
    max_response_bytes: int | None
    timeout_seconds: float | None
    redirects: str
    strict_url_policy: bool

    def __post_init__(self):
        object.__setattr__(self, "configured_hosts", frozenset(self.configured_hosts))
        if self.kind not in {"local_files", "legacy_http", "bounded_http", "official_sdk"}:
            raise ValueError("Unknown transport kind")
        if type(self.strict_url_policy) is not bool:
            raise ValueError("Transport URL enforcement must be explicit")
        if self.kind == "local_files":
            if (self.configured_hosts or self.max_response_bytes is not None or self.timeout_seconds is not None
                    or self.redirects != "not_applicable" or self.strict_url_policy):
                raise ValueError("Local source must not advertise HTTP guarantees")
        elif self.kind == "official_sdk":
            if (not self.configured_hosts or self.max_response_bytes is not None or self.timeout_seconds is not None
                    or self.redirects != "sdk_managed" or self.strict_url_policy):
                raise ValueError("SDK limits must remain explicitly unmanaged")
        else:
            if not self.configured_hosts or type(self.max_response_bytes) is not int or self.max_response_bytes <= 0:
                raise ValueError("HTTP source requires hosts and a positive byte limit")
            if (isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, (int, float))
                    or not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 60):
                raise ValueError("HTTP source requires an explicit bounded timeout")
            if self.kind == "bounded_http" and (not self.strict_url_policy or self.redirects != "forbidden"):
                raise ValueError("Bounded HTTP must enforce URL policy and forbid redirects")
            if self.kind == "legacy_http" and (self.strict_url_policy or self.redirects != "urllib_default"):
                raise ValueError("Legacy HTTP must not claim migrated guarantees")


@dataclass(frozen=True)
class SourceSpec:
    source: str
    entity_types: frozenset[str]
    selection_modes: frozenset[str]
    collection_strategy: str
    revision_kind: str
    revision_validation: str
    revision_nullable: bool
    access_scope: str
    transport: TransportSpec
    capabilities: frozenset[str]

    def __post_init__(self):
        for field in ("entity_types", "selection_modes", "capabilities"):
            object.__setattr__(self, field, frozenset(getattr(self, field)))
        if not isinstance(self.source, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", self.source):
            raise ValueError("Invalid source namespace")
        if not self.entity_types or not self.entity_types <= RESOURCE_TYPES:
            raise ValueError("Unknown resource type")
        if not self.selection_modes or not self.selection_modes <= SELECTION_MODES:
            raise ValueError("Unknown selection mode")
        if not self.collection_strategy or not isinstance(self.collection_strategy, str):
            raise ValueError("Collection strategy description required")
        if self.revision_kind not in {"catalog_commit", "repository_sha", "mutable_container_tag", "none"}:
            raise ValueError("Unknown revision kind")
        if self.revision_validation not in {"sha1_exact", "nonempty_string", "full_hash_if_available", "container_tag", "none"}:
            raise ValueError("Unknown revision validation")
        if type(self.revision_nullable) is not bool:
            raise ValueError("Revision nullability must be explicit")
        if self.access_scope not in {"local_pinned", "anonymous", "sdk_managed"}:
            raise ValueError("Unknown access scope")
        if not isinstance(self.transport, TransportSpec):
            raise ValueError("Transport description required")
        if "metadata" not in self.capabilities or not self.capabilities <= CAPABILITIES:
            raise ValueError("Unknown metadata capability")


def source_index(specs: Iterable[SourceSpec]) -> Mapping[str, SourceSpec]:
    """A read-only design index; duplicate namespaces fail, never replace."""
    result = {}
    for spec in specs:
        if not isinstance(spec, SourceSpec):
            raise ValueError("SourceSpec required")
        if spec.source in result:
            raise ValueError("Duplicate source namespace")
        result[spec.source] = spec
    return MappingProxyType(result)


def _legacy(*hosts: str) -> TransportSpec:
    return TransportSpec("legacy_http", frozenset(hosts), 3_000_000, 20, "urllib_default", False)


def _bounded(host: str) -> TransportSpec:
    return TransportSpec("bounded_http", frozenset({host}), 2_000_000, 20, "forbidden", True)


SOURCE_SPECS = source_index((
    SourceSpec("models.dev", {"model_reference"}, {"first_n_sorted"}, "pinned TOML files",
               "catalog_commit", "sha1_exact", False, "local_pinned",
               TransportSpec("local_files", frozenset(), None, None, "not_applicable", False),
               {"metadata", "offline_fixture", "local_pinning"}),
    SourceSpec("huggingface", {"model_artifact"}, {"exact_ids"}, "targeted repository metadata GET",
               "repository_sha", "nonempty_string", True, "anonymous", _legacy("huggingface.co"),
               {"metadata", "offline_fixture", "explicit_model_relationships", "file_listing", "observed_formats"}),
    SourceSpec("awesome-ai-agents", {"agent_resource"}, {"first_n_unique"}, "pin catalog commit then sample unique entries",
               "catalog_commit", "sha1_exact", False, "anonymous", _legacy("api.github.com", "raw.githubusercontent.com"),
               {"metadata", "offline_fixture", "catalog_pinning"}),
    SourceSpec("nvidia-nim-metadata", {"nim_microservice"}, {"exact_tag"}, "one resourceId and tag metadata GET",
               "mutable_container_tag", "container_tag", False, "anonymous", _legacy("api.ngc.nvidia.com"),
               {"metadata", "offline_fixture", "deployment_profiles"}),
    SourceSpec("modelscope", {"model_artifact"}, {"exact_ids"}, "official SDK get_repo model metadata",
               "repository_sha", "full_hash_if_available", True, "sdk_managed",
               TransportSpec("official_sdk", {"modelscope.cn", "modelscope.ai"}, None, None, "sdk_managed", False),
               {"metadata", "offline_fixture"}),
    SourceSpec("csghub", {"model_artifact"}, {"exact_ids"}, "official csg repository metadata GET at main",
               "repository_sha", "full_hash_if_available", True, "anonymous", _bounded("hub.opencsg.com"),
               {"metadata", "offline_fixture", "file_listing", "observed_formats"}),
    SourceSpec("moark", {"inference_endpoint"}, {"exact_ids"}, "public text roster GET then exact model ID selection",
               "none", "none", True, "anonymous", _bounded("moark.ai"),
               {"metadata", "offline_fixture", "served_model_listing"}),
))
