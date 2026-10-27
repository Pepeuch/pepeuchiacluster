"""B4.3: explicit SourceSpec bindings for local synthetic fixtures only.

No dynamic imports from configuration, SDK, online callable, or database client.
Adapters are imported lazily when their fixture binding is explicitly executed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Callable, Iterable, TYPE_CHECKING

from metadata_primitives import copy_metadata, nonempty_string, strict_json_loads
from source_spec_design import SOURCE_SPECS, SourceSpec

if TYPE_CHECKING:
    from source_adapters import SourceRecord


DEFAULT_MANIFEST = Path(__file__).resolve().parent / "fixtures/discovery_b43.synthetic.json"
MAX_FIXTURE_BYTES = 2_000_000


def _read_object(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        data = handle.read(MAX_FIXTURE_BYTES + 1)
    if len(data) > MAX_FIXTURE_BYTES:
        raise ValueError("Fixture JSON exceeded size limit")
    result = strict_json_loads(data)
    if not isinstance(result, dict):
        raise ValueError("Fixture JSON must be an object")
    return copy_metadata(result)


def _fixture_path(root: Path, value: Any) -> Path:
    relative = Path(nonempty_string(value, "fixture"))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Fixture must stay within its manifest directory")
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Symlinked fixtures are not supported")
    if not path.resolve().is_relative_to(root):
        raise ValueError("Fixture must stay within its manifest directory")
    return path


@dataclass(frozen=True)
class FixtureSelection:
    source: str
    path: Path
    scope: dict[str, Any]
    revision: str | None
    payload_key: str | None

    def payload(self) -> dict[str, Any]:
        data = _read_object(self.path)
        if self.payload_key is not None:
            data = data.get(self.payload_key)
        if not isinstance(data, dict):
            raise ValueError("Selected fixture payload must be an object")
        return data

    def requested_id(self) -> str:
        return self.scope["ids"][0]


@dataclass(frozen=True)
class FixtureBinding:
    spec: SourceSpec
    normalize_fixture: Callable[[FixtureSelection], list[SourceRecord]]

    def collect(self, selection: FixtureSelection) -> list[SourceRecord]:
        if selection.source != self.spec.source:
            raise ValueError("Fixture binding namespace mismatch")
        records = self.normalize_fixture(selection)
        if not records:
            raise ValueError("Fixture selection produced no records")
        for record in records:
            if record.source != self.spec.source or record.entity_type not in self.spec.entity_types:
                raise ValueError("Adapter output differs from SourceSpec")
            if record.source_revision is None and not self.spec.revision_nullable:
                raise ValueError("SourceSpec requires a source revision")
            if self.spec.revision_kind == "none" and record.source_revision is not None:
                raise ValueError("SourceSpec does not declare a source revision")
        mode = selection.scope["mode"]
        if mode == "exact_ids" and [r.source_id for r in records] != selection.scope["ids"]:
            raise ValueError("Fixture identity differs from selected ID")
        if mode == "exact_tag" and (len(records) != 1 or records[0].source_id != selection.scope["resource_id"]
                                    or records[0].source_revision != selection.scope["tag"]):
            raise ValueError("Fixture identity differs from selected resource/tag")
        return records


def _modelsdev(selection: FixtureSelection) -> list[SourceRecord]:
    from collect_discovery_snapshot import collect_modelsdev
    models = selection.path / "models"
    if models.is_symlink() or any(path.is_symlink() for path in models.rglob("*")):
        raise ValueError("Symlinked TOML fixtures are not supported")
    return collect_modelsdev(selection.path, commit=selection.revision, limit=selection.scope["limit"])


def _huggingface(selection: FixtureSelection) -> list[SourceRecord]:
    from source_adapters import normalize_huggingface_model
    return [normalize_huggingface_model(selection.payload())]


def _agents(selection: FixtureSelection) -> list[SourceRecord]:
    from source_adapters import normalize_awesome_catalog
    # Existing B4.0 fixture is one agent entry, not a live complete catalog.
    records = normalize_awesome_catalog({"agents": [selection.payload()]}, source_commit=selection.revision)
    limit = selection.scope["limit"]
    return records[:limit] if limit else records


def _nim(selection: FixtureSelection) -> list[SourceRecord]:
    from source_adapters import normalize_nvidia_nim_metadata
    return [normalize_nvidia_nim_metadata(selection.payload(), resource_id=selection.scope["resource_id"], tag=selection.scope["tag"])]


def _modelscope(selection: FixtureSelection) -> list[SourceRecord]:
    from modelscope_adapter import normalize_modelscope_repo
    return [normalize_modelscope_repo(selection.payload(), requested_id=selection.requested_id())]


def _csghub(selection: FixtureSelection) -> list[SourceRecord]:
    from csghub_adapter import normalize_csghub_model
    return [normalize_csghub_model(selection.payload(), requested_id=selection.requested_id())]


def _moark(selection: FixtureSelection) -> list[SourceRecord]:
    from moark_adapter import select_moark_model
    return [select_moark_model(selection.payload(), requested_id=selection.requested_id())]


FIXTURE_BINDINGS = MappingProxyType({
    source: FixtureBinding(SOURCE_SPECS[source], callback)
    for source, callback in (
        ("models.dev", _modelsdev), ("huggingface", _huggingface),
        ("awesome-ai-agents", _agents), ("nvidia-nim-metadata", _nim),
        ("modelscope", _modelscope), ("csghub", _csghub), ("moark", _moark),
    )
})


def _selection(source: str, entry: Any, root: Path) -> FixtureSelection:
    spec = SOURCE_SPECS[source]
    if not isinstance(entry, dict) or not {"fixture", "scope"} <= entry.keys() or entry.keys() - {"fixture", "scope", "revision", "payload_key"}:
        raise ValueError("Invalid fixture selection fields")
    scope = copy_metadata(entry["scope"])
    if not isinstance(scope, dict) or scope.get("mode") not in spec.selection_modes:
        raise ValueError("Fixture selection mode differs from SourceSpec")
    mode = scope["mode"]
    fields = {"mode"}
    if mode == "exact_ids":
        fields.add("ids")
        ids = scope.get("ids")
        if not isinstance(ids, list) or len(ids) != 1:
            raise ValueError("Exactly one ID per fixture is supported")
        nonempty_string(ids[0], "ids[]")
    elif mode in ("first_n_sorted", "first_n_unique"):
        fields.add("limit")
        if type(scope.get("limit")) is not int or scope["limit"] < 0:
            raise ValueError("Fixture limit must be a nonnegative integer")
    elif mode == "exact_tag":
        fields.update({"resource_id", "tag"})
        nonempty_string(scope.get("resource_id"), "resource_id")
        nonempty_string(scope.get("tag"), "tag")
    if source in ("modelscope", "csghub"):
        fields.add("endpoint")
        if scope.get("endpoint") not in {f"https://{host}" for host in spec.transport.configured_hosts}:
            raise ValueError("Fixture endpoint differs from SourceSpec")
    if source == "csghub":
        fields.update({"source", "revision_request"})
        if scope.get("source") != "csg" or scope.get("revision_request") != "main":
            raise ValueError("Unsupported CSGHub fixture provenance")
    if source == "moark":
        from moark_adapter import API_BASE, CATALOG_URL
        fields.update({"endpoint", "catalog_url", "authentication", "input"})
        if (scope.get("endpoint") != API_BASE or scope.get("catalog_url") != CATALOG_URL
                or scope.get("authentication") != "anonymous" or scope.get("input") != "synthetic_fixture"):
            raise ValueError("Unsupported MoArk fixture provenance")
    if set(scope) != fields:
        raise ValueError("Unexpected fixture scope fields")
    revision = entry.get("revision")
    if source in ("models.dev", "awesome-ai-agents"):
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("Pinned fixture catalog commit required")
    elif revision is not None:
        raise ValueError("Fixture revision must come from source metadata or selected tag")
    payload_key = entry.get("payload_key")
    if payload_key is not None:
        nonempty_string(payload_key, "payload_key")
    if source == "models.dev" and payload_key is not None:
        raise ValueError("TOML fixtures do not have a JSON payload key")
    return FixtureSelection(source, _fixture_path(root, entry["fixture"]), scope, revision, payload_key)


def discover_fixtures(manifest_path: Path = DEFAULT_MANIFEST, *, sources: Iterable[str] | None = None,
                      captured_at: str | None = None) -> dict[str, Any]:
    """Prepare one complete synthetic snapshot, or fail without partial output."""
    selected = tuple(FIXTURE_BINDINGS) if sources is None else tuple(sources)
    if not selected or len(set(selected)) != len(selected) or any(source not in FIXTURE_BINDINGS for source in selected):
        raise ValueError("Select distinct registered sources")
    manifest_path = Path(manifest_path)
    manifest = _read_object(manifest_path)
    if (set(manifest) != {"format", "synthetic", "captured_at", "sources"}
            or manifest.get("format") != "pepeuch-ai.fixture-discovery/v1" or manifest.get("synthetic") is not True
            or not isinstance(manifest.get("sources"), dict)
            or set(manifest["sources"]) - SOURCE_SPECS.keys()):
        raise ValueError("An explicit synthetic fixture manifest is required")
    if any(source not in manifest["sources"] for source in selected):
        raise ValueError("Requested source missing from fixture manifest")
    nonempty_string(manifest.get("captured_at"), "captured_at")
    selections = [_selection(source, manifest["sources"][source], manifest_path.parent.resolve()) for source in selected]
    records = []
    for selection in selections:
        records.extend(FIXTURE_BINDINGS[selection.source].collect(selection))
    from discovery_cache import make_snapshot, validate_snapshot
    snapshot = make_snapshot(records, scope={s.source: s.scope for s in selections},
                             captured_at=manifest["captured_at"] if captured_at is None else captured_at)
    return validate_snapshot(snapshot)
