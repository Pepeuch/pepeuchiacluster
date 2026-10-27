CREATE TABLE worker_identities (
 id TEXT PRIMARY KEY, status TEXT NOT NULL CHECK(status IN ('active','revoked')),
 credential_sha256 TEXT NOT NULL, credential_epoch INTEGER NOT NULL CHECK(credential_epoch >= 1),
 capabilities TEXT NOT NULL, limits TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE attempt_worker_epochs (
 attempt_id TEXT PRIMARY KEY REFERENCES attempts(id), credential_epoch INTEGER NOT NULL
);
INSERT INTO attempt_worker_epochs SELECT id,1 FROM attempts;
UPDATE operations SET actor='fake-cpu@1' WHERE actor='fake-cpu';
