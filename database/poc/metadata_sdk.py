"""B4.2: injectable repository SDK seam; no optional SDK import or HTTP clone."""

from __future__ import annotations

from typing import Any, Protocol


class RepositoryInfo(Protocol):
    def to_dict(self) -> dict[str, Any]: ...


class RepositoryClient(Protocol):
    def get_repo(self, repo_id: str, *, repo_type: str) -> RepositoryInfo: ...


class MetadataSDKError(RuntimeError):
    pass


def read_model_repository(client: RepositoryClient, requested_id: str) -> dict[str, Any]:
    """Only call model metadata; provider normalization owns JSON conversion.

    The SDK retains its own network, authentication and timeout policy. This
    seam does not claim to enforce HTTPPolicy or anonymous access for a SDK.
    """
    try:
        data = client.get_repo(requested_id, repo_type="model").to_dict()
    except Exception:
        raise MetadataSDKError("Repository SDK metadata unavailable") from None
    if not isinstance(data, dict):
        raise ValueError("Repository SDK metadata must be an object")
    return data
