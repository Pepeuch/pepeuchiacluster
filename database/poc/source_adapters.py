"""Pure, database-independent adapters for external discovery snapshots.

This is a schema-compatibility POC, not a network collector or a catalog import.
Only explicit source relationships are kept; names never imply identity.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Literal


EntityType = Literal["model_artifact", "agent_resource", "nim_microservice"]


@dataclass(frozen=True)
class SourceRecord:
    source: str
    source_id: str
    source_revision: str | None
    entity_type: EntityType
    display_name: str
    attributes: dict[str, Any]
    relationships: tuple[dict[str, str], ...]
    raw_metadata: dict[str, Any]


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value


def _optional_string(value: Any, field: str) -> str | None:
    return None if value is None else _string(value, field)


def _optional_strings(value: Any, field: str) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list of strings")
    return [_string(item, field) for item in value]


def _base_models(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [_string(value, "cardData.base_model")]
    return _optional_strings(value, "cardData.base_model")


def _gating(value: Any) -> tuple[str, str | None]:
    # Hugging Face uses false, true, "auto" or "manual". A missing value
    # is unknown, not equivalent to public access.
    if value is None:
        return "unknown", None
    if value is False:
        return "public", None
    if value is True:
        return "gated", "unspecified"
    if value in ("auto", "manual"):
        return "gated", value
    raise ValueError(f"Unexpected Hugging Face gated value: {value!r}")


def normalize_huggingface_model(data: dict[str, Any]) -> SourceRecord:
    """Normalize one public HF /api/models/{repo_id} response without guesses."""
    data = _object(data, "huggingface model")
    model_id = _string(data.get("id"), "id")
    revision = _optional_string(data.get("sha"), "sha")
    card = _object(data["cardData"], "cardData") if data.get("cardData") is not None else {}
    config = _object(data["config"], "config") if data.get("config") is not None else {}
    base_models = _base_models(card.get("base_model"))
    architecture = _optional_strings(config.get("architectures"), "config.architectures")
    license_name = _optional_string(card.get("license"), "cardData.license")
    access, approval_mode = _gating(data.get("gated"))

    files: list[str] | None = None
    if data.get("siblings") is not None:
        siblings = data["siblings"]
        if not isinstance(siblings, list):
            raise ValueError("siblings must be a list")
        files = [_string(_object(item, "siblings[]").get("rfilename"), "siblings[].rfilename")
                 for item in siblings]

    # Positive format observations only; absent metadata is not a negative
    # assertion, especially for gated or partially populated API responses.
    available_formats: list[str] = []
    if data.get("gguf") is not None or (files is not None and any(f.lower().endswith(".gguf") for f in files)):
        available_formats.append("gguf")
    if data.get("safetensors") is not None or (files is not None and any(f.lower().endswith(".safetensors") for f in files)):
        available_formats.append("safetensors")

    relationships = tuple(
        {"relation": "declared_base_model", "source": "huggingface", "target_id": parent}
        for parent in (base_models or [])
    )
    return SourceRecord(
        source="huggingface",
        source_id=model_id,
        source_revision=revision,
        entity_type="model_artifact",
        display_name=model_id.rsplit("/", 1)[-1],
        attributes={
            "access": access,
            "approval_mode": approval_mode,
            "license": license_name,
            "architectures": architecture,
            "base_models": base_models,
            "available_formats": available_formats,
            "file_count": len(files) if files is not None else None,
        },
        relationships=relationships,
        raw_metadata=data,
    )


def normalize_awesome_agent(data: dict[str, Any], *, source_commit: str) -> SourceRecord:
    """Normalize one entry of a pinned awesome-ai-agents JSON snapshot."""
    data = _object(data, "awesome agent")
    revision = _string(source_commit, "source_commit")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("source_commit must be a pinned lowercase Git SHA-1")
    agent_id = _string(data.get("id"), "id")
    project = _string(data.get("project"), "project")
    categories = _optional_strings(data.get("categories"), "categories")
    raw_sources = data.get("sources")
    if raw_sources is not None and not isinstance(raw_sources, list):
        raise ValueError("sources must be a list")
    urls = [] if raw_sources is not None else None
    for item in raw_sources or []:
        source = _object(item, "sources[]")
        url = source.get("source_url")
        if url is not None:
            urls.append(_string(url, "sources[].source_url"))
    public = data.get("has_public_repository")
    if public is not None and not isinstance(public, bool):
        raise ValueError("has_public_repository must be a boolean or null")
    description = _optional_string(data.get("project_description"), "project_description")

    return SourceRecord(
        source="awesome-ai-agents",
        source_id=agent_id,
        source_revision=revision,
        entity_type="agent_resource",
        display_name=project,
        attributes={
            "description": description,
            "categories": categories,
            "has_public_repository": public,
            "source_urls": urls,
            "source_count": len(raw_sources) if raw_sources is not None else None,
        },
        relationships=(),
        raw_metadata=data,
    )


def normalize_awesome_catalog(data: dict[str, Any], *, source_commit: str) -> list[SourceRecord]:
    catalog = _object(data, "awesome catalog")
    agents = catalog.get("agents")
    if not isinstance(agents, list):
        raise ValueError("awesome catalog requires an agents list")
    unique: dict[str, SourceRecord] = {}
    for agent in agents:
        record = normalize_awesome_agent(agent, source_commit=source_commit)
        prior = unique.get(record.source_id)
        if prior is not None:
            if prior.raw_metadata != record.raw_metadata:
                raise ValueError(f"awesome catalog has conflicting agent ID: {record.source_id}")
            # Upstream can repeat an identical entry; record one logical item.
            continue
        unique[record.source_id] = record
    return list(unique.values())


def _optional_bool(value: Any, field: str) -> bool | None:
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _optional_positive_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _optional_nonnegative_number(value: Any, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a nonnegative number")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field} must be a finite nonnegative number")
    return float(value)


def _gpu_targets(value: Any, field: str) -> list[str] | None:
    """NVIDIA currently emits strings; future releases may emit arrays."""
    if value is None:
        return None
    if isinstance(value, str):
        return [_string(value, field)]
    return _optional_strings(value, field)


def _pci_device(value: str) -> str:
    """NIM notation is PCI device:vendor, the reverse of lspci vendor:device."""
    if not re.fullmatch(r"[0-9a-fA-F]{4}:[0-9a-fA-F]{4}", value):
        raise ValueError(f"Invalid NVIDIA PCI device:vendor identifier: {value!r}")
    return value.lower()


def _normalize_nim_profile(data: dict[str, Any]) -> dict[str, Any]:
    data = _object(data, "profiles[]")
    profile_id = _string(data.get("profile_id"), "profiles[].profile_id")
    targets = _gpu_targets(data.get("gpu_device"), "profiles[].gpu_device")
    tested = _optional_strings(data.get("tested_gpu_devices"), "profiles[].tested_gpu_devices")
    if tested is None:
        raise ValueError("profiles[].tested_gpu_devices is required (empty list is valid)")
    return {
        "profile_id": profile_id,  # Opaque identifier; never parse its structure.
        "gpu": _gpu_targets(data.get("gpu"), "profiles[].gpu"),
        "gpu_device": [_pci_device(device) for device in targets] if targets is not None else None,
        "tested_gpu_devices": [_pci_device(device) for device in tested],
        "precision": _optional_string(data.get("precision"), "profiles[].precision"),
        "inference_backend": _optional_string(data.get("inference_backend"), "profiles[].inference_backend"),
        "tensor_parallel_size": _optional_positive_int(data.get("tensor_parallel_size"), "profiles[].tensor_parallel_size"),
        "pipeline_parallel_size": _optional_positive_int(data.get("pipeline_parallel_size"), "profiles[].pipeline_parallel_size"),
        "max_gpu_count": _optional_positive_int(data.get("max_gpu_count"), "profiles[].max_gpu_count"),
        "min_vram_per_device_gb": _optional_nonnegative_number(data.get("min_vram_per_device_gb"), "profiles[].min_vram_per_device_gb"),
        "min_driver_version": _optional_string(data.get("min_driver_version"), "profiles[].min_driver_version"),
        "min_cpu_count": _optional_positive_int(data.get("min_cpu_count"), "profiles[].min_cpu_count"),
        "system_memory_per_device_gb": _optional_nonnegative_number(data.get("system_memory_per_device_gb"), "profiles[].system_memory_per_device_gb"),
        "disk_space_per_device_gb": _optional_nonnegative_number(data.get("disk_space_per_device_gb"), "profiles[].disk_space_per_device_gb"),
        "feat_lora": _optional_bool(data.get("feat_lora"), "profiles[].feat_lora"),
        "workspace_hash": _optional_string(data.get("workspace_hash"), "profiles[].workspace_hash"),
    }


def normalize_nvidia_nim_metadata(
    data: dict[str, Any], *, resource_id: str, tag: str,
) -> SourceRecord:
    """Normalize public NIM metadata for a precise container resource/tag.

    This is a *deployment microservice*, not an HF model and not evidence
    of registry entitlement or successful execution on target hardware.
    """
    data = _object(data, "NVIDIA NIM metadata")
    resource_id = _string(resource_id, "resource_id")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+){1,2}", resource_id):
        raise ValueError("NIM resource_id must have two or three path segments")
    tag = _string(tag, "tag")
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", tag):
        raise ValueError("NIM tag must be a container tag, separate from resource_id")
    raw_profiles = data.get("profiles")
    if raw_profiles is not None and not isinstance(raw_profiles, list):
        raise ValueError("profiles must be a list")
    profiles = [_normalize_nim_profile(p) for p in raw_profiles] if raw_profiles is not None else None
    features = _object(data["features"], "features") if data.get("features") is not None else {}
    release = _object(data["release_details"], "release_details") if data.get("release_details") is not None else {}
    related = _optional_strings(data.get("related_urls"), "related_urls")
    context = data.get("features", {}).get("context_window") if features else None
    if context is not None and (isinstance(context, bool) or not isinstance(context, int) or context < 0):
        raise ValueError("features.context_window must be a nonnegative integer")

    return SourceRecord(
        source="nvidia-nim-metadata",
        source_id=resource_id,
        source_revision=tag,  # Mutable image TAG, not a Git SHA or digest.
        entity_type="nim_microservice",
        display_name=resource_id.rsplit("/", 1)[-1],
        attributes={
            "profiles": profiles,
            "profiles_count": len(profiles) if profiles is not None else None,
            "container_version": _optional_string(release.get("container_version"), "release_details.container_version"),
            "tool_calling": _optional_bool(features.get("tool_calling"), "features.tool_calling"),
            "vgpu_support": _optional_bool(features.get("vgpu_support"), "features.vgpu_support"),
            "context_window": context,
            "related_urls": related,
            "registry_entitlement": "unknown",  # Public metadata cannot grant access.
        },
        relationships=(),  # A similar name never proves model identity.
        raw_metadata=data,
    )


@dataclass(frozen=True)
class GpuTarget:
    pci_device: str
    vram_per_device_gb: float
    gpu_count: int


def assess_nim_gpu_profile(profile: dict[str, Any], *, hardware: GpuTarget) -> dict[str, Any]:
    """Conservative recorded-constraints screen, NEVER proof of runtime support.

    Caller supplies a *normalized* profile. Driver/host resources, entitlement,
    architecture support and virtualization are not verified by this screen.
    """
    target = _pci_device(hardware.pci_device)
    vram = _optional_nonnegative_number(hardware.vram_per_device_gb, "hardware.vram_per_device_gb")
    count = _optional_positive_int(hardware.gpu_count, "hardware.gpu_count")
    if vram is None or count is None:
        raise ValueError("hardware vRAM and GPU count must be provided")

    targets = profile["gpu_device"]
    tested = profile["tested_gpu_devices"]
    if targets is not None and target in targets:
        match = "direct"
    elif target in tested:
        match = "tested"
    elif profile["gpu"] is None and targets is None:
        match = "gpu_agnostic"
    else:
        match = "other_gpu"

    blocking = []
    unverified = []
    if match == "other_gpu":
        blocking.append("target_gpu_not_listed")
    required = (profile["tensor_parallel_size"] or 1) * (profile["pipeline_parallel_size"] or 1)
    if required > count:
        blocking.append("insufficient_gpu_count")
    max_gpus = profile["max_gpu_count"]
    if max_gpus is not None and required > max_gpus:
        blocking.append("profile_gpu_count_inconsistent")
    floor = profile["min_vram_per_device_gb"]
    if floor is None:
        unverified.append("minimum_vram_not_published")
    elif floor > vram:
        blocking.append("insufficient_vram_per_gpu")
    for field in ("min_driver_version", "min_cpu_count", "system_memory_per_device_gb", "disk_space_per_device_gb"):
        if profile[field] is not None:
            unverified.append(field + "_not_checked")

    return {
        "profile_id": profile["profile_id"],
        "targeting": match,
        "status": "excluded" if blocking else ("candidate_unverified" if unverified else "candidate_recorded_constraints_met"),
        "required_gpus": required,
        "blocking_reasons": blocking,
        "unverified_requirements": unverified,
        "runtime_verified": False,
    }
