#!/usr/bin/env python3
"""Read-only, bounded online contract probe for HF, agents, and NVIDIA NIM.

No weights or repositories are downloaded, and no database is contacted.
The output is a compact JSON summary without tokens or full metadata.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from source_adapters import (
    GpuTarget,
    assess_nim_gpu_profile,
    normalize_awesome_catalog,
    normalize_huggingface_model,
    normalize_nvidia_nim_metadata,
)


HF_MODELS = (
    "google/gemma-3-1b-it",
    "ggml-org/gemma-3-1b-it-GGUF",
)
AGENTS_REPO = "slavakurilyak/awesome-ai-agents"
MAX_RESPONSE_BYTES = 3_000_000
NIM_RESOURCE = "nim/nvidia/parakeet-1-1b-rnnt-multilingual"
NIM_TAG = "1.5.0"
# A2000 physical PCI identity from the Proxmox host; NOT accessible inside VM.
NIM_HARDWARE = GpuTarget(pci_device="2571:10de", vram_per_device_gb=12, gpu_count=1)


def get_json(url: str, timeout: int) -> dict:
    request = Request(url, headers={
        "User-Agent": "Pepeuch-AI-Cluster-source-contract-POC/0.1",
        "Accept": "application/json",
    })
    with urlopen(request, timeout=timeout) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("Source response exceeds audit size limit")
    result = json.loads(body)
    if not isinstance(result, dict):
        raise ValueError("Source response must be a JSON object")
    return result


def audit(timeout: int) -> dict:
    hf_results = []
    for repo_id in HF_MODELS:
        data = get_json(f"https://huggingface.co/api/models/{quote(repo_id, safe='/')}", timeout)
        record = normalize_huggingface_model(data)
        if record.source_id != repo_id:
            raise ValueError(f"Hugging Face response identity mismatch: {repo_id}")
        hf_results.append({
            "id": record.source_id,
            "sha": record.source_revision,
            "entity_type": record.entity_type,
            "attributes": record.attributes,
            "relationships": list(record.relationships),
        })

    # Resolve the moving GitHub branch to an immutable commit first.
    commit = get_json(f"https://api.github.com/repos/{AGENTS_REPO}/commits/main", timeout).get("sha")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Cannot resolve a pinned awesome-ai-agents commit")
    agents_data = get_json(
        f"https://raw.githubusercontent.com/{AGENTS_REPO}/{commit}/awesome-agents.json",
        timeout,
    )
    agents = normalize_awesome_catalog(agents_data, source_commit=commit)
    total_entries = len(agents_data["agents"])
    return {
        "scope": "read-only metadata contract probe; not database ingestion",
        "huggingface": hf_results,
        "awesome_ai_agents": {
            "commit": commit,
            "raw_entries": total_entries,
            "unique_resources": len(agents),
            "exact_duplicate_rows": total_entries - len(agents),
            "entity_type": "agent_resource",
            "sample": [{"id": item.source_id, "project": item.display_name}
                       for item in agents[:3]],
        },
    }


def audit_nvidia_nim(timeout: int, *, resource_id: str, tag: str) -> dict:
    # Validate resource and tag before building a URL. The API is publicly
    # readable; this does not request registry tokens or download containers.
    normalize_nvidia_nim_metadata({}, resource_id=resource_id, tag=tag)
    query = urlencode({"resourceId": resource_id, "tag": tag})
    try:
        metadata = get_json(f"https://api.ngc.nvidia.com/v2/nim/metadata?{query}", timeout)
    except HTTPError as exc:
        if exc.code == 404:
            # NVIDIA documents this as no metadata for this exact tag,
            # NOT evidence that the container doesn't exist.
            return {
                "resource_id": resource_id,
                "tag": tag,
                "metadata_status": "unavailable_for_tag",
            }
        raise

    record = normalize_nvidia_nim_metadata(metadata, resource_id=resource_id, tag=tag)
    profiles = record.attributes["profiles"]
    assessments = [assess_nim_gpu_profile(p, hardware=NIM_HARDWARE) for p in (profiles or [])]
    status_counts = Counter(a["status"] for a in assessments)
    target_counts = Counter(a["targeting"] for a in assessments)
    return {
        "resource_id": record.source_id,
        "tag": record.source_revision,
        "entity_type": record.entity_type,
        "metadata_status": "available",
        "profiles_count": record.attributes["profiles_count"],
        "profiles_missing_vram": sum(p["min_vram_per_device_gb"] is None for p in (profiles or [])),
        "target_hardware": {
            "gpu": "NVIDIA RTX A2000 12GB (physical host, no VM passthrough)",
            "pci_device": NIM_HARDWARE.pci_device,
            "vram_per_device_gb": NIM_HARDWARE.vram_per_device_gb,
            "gpu_count": NIM_HARDWARE.gpu_count,
        },
        "targeting_counts": dict(sorted(target_counts.items())),
        "screening_counts": dict(sorted(status_counts.items())),
        "tool_calling": record.attributes["tool_calling"],
        "vgpu_support": record.attributes["vgpu_support"],
        "registry_entitlement": "unknown",
        "note": "Recorded-constraints screen only; NOT driver, VM passthrough, license, or runtime validation",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--nim-only", action="store_true", help="Probe only one NVIDIA NIM metadata document")
    parser.add_argument("--include-nim", action="store_true", help="Append NVIDIA NIM to HF and agent probes")
    parser.add_argument("--nim-resource-id", default=NIM_RESOURCE)
    parser.add_argument("--nim-tag", default=NIM_TAG)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 60:
        parser.error("--timeout must be between 1 and 60 seconds")
    try:
        if args.nim_only:
            result = {"scope": "read-only NVIDIA NIM metadata probe", "nvidia_nim": audit_nvidia_nim(
                args.timeout, resource_id=args.nim_resource_id, tag=args.nim_tag,
            )}
        else:
            result = audit(args.timeout)
            if args.include_nim:
                result["nvidia_nim"] = audit_nvidia_nim(
                    args.timeout, resource_id=args.nim_resource_id, tag=args.nim_tag,
                )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"Source audit failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
