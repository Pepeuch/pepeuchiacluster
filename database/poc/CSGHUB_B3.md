# B3.2 — CSGHub/OpenCSG model repository metadata POC

**Scope:** read-only one-repository metadata snapshot; no model files or weights,
no authentication, inference, DB ingestion, mass crawling, or account actions.

## Official upstream evidence (2026-10-27)

- OpenCSG's official platform SDK: `https://github.com/OpenCSGs/csghub-sdk`
  (inspected HEAD `f9f6f5e79523e2ca32fbda73a6c4571f1af4b7ac`).
- `pycsghub/utils.py`: `model_info()` calls `get_repo_meta_path(repo_type="model", ...)`,
  performs a single GET, constructs `huggingface_hub.hf_api.ModelInfo` from JSON.
- The SDK's current default source is `csg`; for public repository metadata
  it builds `/csg/api/models/{namespace}/{name}/revision/main` from the hub
  endpoint `https://hub.opencsg.com`. This differs from the AI Gateway's
  `/v1/models`, which lists **served inference resources**, not model files.
- Upstream docs: `https://www.opencsg.com/docs/en/other/api_and_sdk` and
  `https://github.com/OpenCSGs/csghub-sdk/blob/main/doc/sdk.md`.

One bounded anonymous GET to
`https://hub.opencsg.com/csg/api/models/OpenCSG/csg-wukong-1B/revision/main`
returned a root JSON object with `id`, `sha`, `private`, `tags`, `downloads`,
`likes`, `siblings`, timestamps, author and library/pipeline metadata. At the
time of verification, `sha` was `15d1adc678c581219d44b07024f8d3b2dd201746`
and `siblings` contained 9 entries. This is a **live observation**, not a
guarantee of continued availability or content stability.

## B2 contract

- `source="csghub"`, `entity_type="model_artifact"`, `source_id=namespace/name`.
- The cache's identity is independent from Hugging Face and ModelScope, even
  when repository names coincide; infer no canonical model or parent link.
- `source_revision` is only a full explicit immutable SHA from `sha`, not the
  mutable branch name, a timestamp, or a DB numeric identifier.
- `private=false` establishes **public listing visibility**, but an absent
  `gated` flag leaves download `access="unknown"`. Gating and privacy are
  separate; a repository being public does not prove free download access.
- The public example has a bare tag `apache-2.0` but no explicit license
  field. `license` is therefore **null**, rather than guessed from that tag.
  An explicit `license` or `cardData.license` would be accepted; conflict fails.
- `file_count` reflects returned `siblings`, not downloaded files. GGUF and
  safetensors are observed only from explicit filenames. Absent files list
  stays `null`; an explicit empty list remains `0` / `[]`.
- Preserve a credential-free copy of other source metadata in `raw_metadata`;
  fail closed on invalid types or schema contradictions.

## Offline probe (no internet or optional SDK dependencies)

```bash
cd /opt/pepeuch-ai/repo
python3 -m unittest discover -s database/poc -p 'test_*.py' -q
python3 database/poc/probe_csghub.py \
  --fixture database/poc/fixtures/csghub_model_info.synthetic.json \
  > /opt/pepeuch-ai/data/discovery-poc/csghub-SYNTHETIC-DO-NOT-IMPORT.json
```

The fixture is entirely synthetic and must not be imported as real metadata.

## Real one-model metadata probe

```bash
python3 database/poc/probe_csghub.py \
  --online --model-id OpenCSG/csg-wukong-1B \
  > /opt/pepeuch-ai/data/discovery-poc/csghub-live.json
```

`probe_csghub.py` uses Python's standard library HTTP client; no SDK install is
needed. The URL is fixed to the official HTTPS domain, the identity is
validated, redirects are denied, the response is limited to 2 MB, and HTTP
errors do not echo bodies or tokens. The `source="csg"` route deliberately
avoids cross-platform mirrors (`hf`, `ms`, `xet`) exposed by upstream.

The result is a validated B2 JSON snapshot on stdout. Stderr contains only
status/errors. **Do not import it** into PG/SurrealDB before checking the
source ID, SHA, license/access semantics and normalized payload.

## Explicit limitations / next steps

1. Run this probe on the VM, verify the live response contract and snapshot.
2. Consider a separately declared second model with confirmed release and
   access status, then test B2 repeat/upsert on both databases.
3. Investigate official CSGHub `dataset`, `space`, `code`, `mcp` and `skill`
   repository APIs with separate entity types. This POC only supports models.
4. CSGHub **AI Gateway** `/v1/models` is a separate, served-model catalog;
   avoid conflating those endpoints with downloadable `model_artifact`s.
5. B3.3 MoArk similarly needs its own service/endpoint identity contract.
