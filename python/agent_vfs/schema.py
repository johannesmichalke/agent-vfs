import re


def validate_table_name(name: str) -> str:
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
        raise ValueError(
            f'Invalid table name: "{name}". Must contain only letters, numbers, '
            "and underscores, and start with a letter or underscore."
        )
    return name


def get_sqlite_schema(table_name: str = "nodes") -> str:
    t = validate_table_name(table_name)
    return f"""\
CREATE TABLE IF NOT EXISTS {t} (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  path        TEXT NOT NULL,
  parent_path TEXT NOT NULL,
  name        TEXT NOT NULL,
  is_dir      INTEGER DEFAULT 0,
  content     TEXT,
  summary     TEXT,
  version     INTEGER DEFAULT 1,
  size        INTEGER DEFAULT 0,
  created_at  TEXT DEFAULT (datetime('now')),
  updated_at  TEXT DEFAULT (datetime('now')),
  UNIQUE(user_id, path)
);
CREATE INDEX IF NOT EXISTS idx_{t}_ls ON {t}(user_id, parent_path);
CREATE INDEX IF NOT EXISTS idx_{t}_name ON {t}(user_id, name);
CREATE INDEX IF NOT EXISTS idx_{t}_updated ON {t}(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS {t}_tags (
  user_id    TEXT NOT NULL,
  path       TEXT NOT NULL,
  tag        TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (user_id, path, tag)
);
CREATE INDEX IF NOT EXISTS idx_{t}_tags_lookup ON {t}_tags(user_id, tag);

CREATE VIRTUAL TABLE IF NOT EXISTS {t}_fts USING fts5(
  content,
  summary,
  user_id UNINDEXED,
  path UNINDEXED,
  tokenize='porter unicode61'
);

CREATE TABLE IF NOT EXISTS {t}_chunks (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  node_path   TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  content     TEXT NOT NULL,
  UNIQUE(user_id, node_path, chunk_index)
)"""


def get_postgres_schema(table_name: str = "nodes") -> str:
    t = validate_table_name(table_name)
    return f"""\
CREATE TABLE IF NOT EXISTS {t} (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  path        TEXT NOT NULL,
  parent_path TEXT NOT NULL,
  name        TEXT NOT NULL,
  is_dir      BOOLEAN DEFAULT FALSE,
  content     TEXT,
  summary     TEXT,
  version     INTEGER DEFAULT 1,
  size        INTEGER DEFAULT 0,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, path)
);
CREATE INDEX IF NOT EXISTS idx_{t}_ls ON {t}(user_id, parent_path);
CREATE INDEX IF NOT EXISTS idx_{t}_name ON {t}(user_id, name);
CREATE INDEX IF NOT EXISTS idx_{t}_updated ON {t}(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS {t}_tags (
  user_id    TEXT NOT NULL,
  path       TEXT NOT NULL,
  tag        TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (user_id, path, tag)
);
CREATE INDEX IF NOT EXISTS idx_{t}_tags_lookup ON {t}_tags(user_id, tag)"""


sqlite_schema = get_sqlite_schema()
postgres_schema = get_postgres_schema()
