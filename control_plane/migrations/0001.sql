CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, sha256 TEXT NOT NULL);
CREATE TABLE workspaces (id TEXT PRIMARY KEY, owner TEXT NOT NULL, project TEXT NOT NULL);
CREATE TABLE missions (
 id TEXT PRIMARY KEY, owner TEXT NOT NULL, project TEXT NOT NULL,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id), title TEXT NOT NULL,
 objective TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN
 ('draft','approved','queued','running','completed','failed','cancel_requested','cancelled','interrupted')),
 created_at TEXT NOT NULL, authorized_files TEXT NOT NULL
);
CREATE TABLE tasks (
 id TEXT PRIMARY KEY, mission_id TEXT NOT NULL UNIQUE REFERENCES missions(id),
 role TEXT NOT NULL, capability TEXT NOT NULL, worker_id TEXT NOT NULL,
 state TEXT NOT NULL, plan TEXT NOT NULL
);
CREATE TABLE attempts (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), number INTEGER NOT NULL,
 worker_id TEXT NOT NULL, state TEXT NOT NULL, generation TEXT NOT NULL UNIQUE,
 started_at TEXT NOT NULL, deadline REAL NOT NULL, expected_version TEXT,
 result_sha256 TEXT, error_code TEXT, UNIQUE(task_id, number)
);
CREATE TABLE files (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
 name TEXT NOT NULL COLLATE NOCASE, UNIQUE(workspace_id, name)
);
CREATE TABLE versions (
 id TEXT PRIMARY KEY, file_id TEXT NOT NULL REFERENCES files(id), number INTEGER NOT NULL,
 size INTEGER NOT NULL CHECK(size >= 0), sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
 mission_id TEXT REFERENCES missions(id), attempt_id TEXT REFERENCES attempts(id),
 UNIQUE(file_id, number)
);
CREATE TABLE results (
 id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL UNIQUE REFERENCES attempts(id),
 version_id TEXT NOT NULL REFERENCES versions(id), provenance TEXT NOT NULL
);
CREATE TABLE events (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
 mission_id TEXT REFERENCES missions(id), workspace_id TEXT NOT NULL REFERENCES workspaces(id),
 actor TEXT NOT NULL, at TEXT NOT NULL, type TEXT NOT NULL, details TEXT NOT NULL
);
CREATE TABLE operations (
 actor TEXT NOT NULL, id TEXT NOT NULL, request_sha256 TEXT NOT NULL, response TEXT NOT NULL,
 PRIMARY KEY(actor, id)
);
CREATE INDEX missions_owner ON missions(owner, created_at);
CREATE INDEX events_mission ON events(mission_id, sequence);
