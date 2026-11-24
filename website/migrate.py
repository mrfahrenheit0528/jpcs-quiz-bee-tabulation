"""Explicit SQLite migration and consistent backups; never seed or reconcile scores."""
from pathlib import Path
import os
import sqlite3
from datetime import datetime, timezone

SCHEMA_VERSION = 1

def backup(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target or target.exists():
        raise RuntimeError('Backup destination must be a new file, distinct from the source.')
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(source.as_uri()+'?mode=ro', uri=True, timeout=10) as src:
            with sqlite3.connect(target) as dst:
                src.backup(dst)
                # Standalone backup must not require writable WAL sidecars on import.
                dst.execute('PRAGMA journal_mode=DELETE')
                if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('SQLite backup failed integrity_check.')
        os.chmod(target, 0o600)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target

def migrate(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise RuntimeError(f'Database missing: {path}. Import an existing database; seed.py is never run.')
    with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as conn:
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Database failed integrity_check; restore a verified backup.')
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'user', 'school', 'round', 'score', 'event'} <= tables:
            raise RuntimeError('Not a quiz database: required tables are missing.')
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(f'Database schema {version} is newer than supported {SCHEMA_VERSION}; use matching code.')
        duplicates = conn.execute('SELECT round_id,school_id,question_number,COUNT(*) FROM score GROUP BY 1,2,3 HAVING COUNT(*)>1 LIMIT 20').fetchall()
        if duplicates:
            raise RuntimeError(f'Duplicate score keys (round,school,question,count): {duplicates}. Reconcile a COPY before migration; no rows were changed.')
        if version == SCHEMA_VERSION:
            expected={'uq_score_answer':('round_id','school_id','question_number'),
                      'ix_score_school':('school_id',), 'ix_round_event_number':('event_id','number'),
                      'ix_school_event_user':('event_id','user_id')}
            for name, columns in expected.items():
                actual=tuple(row[2] for row in conn.execute(f'PRAGMA index_info("{name}")'))
                if actual!=columns:
                    raise RuntimeError(f'Schema version 1 is missing or has an invalid {name} index. Restore a verified backup.')
            unique={row[1]:row[2] for row in conn.execute('PRAGMA index_list("score")')}
            if not unique.get('uq_score_answer'):
                raise RuntimeError('Score key index is not unique. Restore a verified backup.')
    if version == SCHEMA_VERSION:
        return None
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    saved = backup(path, path.parent/'backups'/f'pre-v{SCHEMA_VERSION}-{stamp}.db')
    with sqlite3.connect(path, timeout=10) as conn:
        conn.execute('BEGIN IMMEDIATE')
        try:
            conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_score_answer ON score(round_id,school_id,question_number)')
            conn.execute('CREATE INDEX IF NOT EXISTS ix_score_school ON score(school_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS ix_round_event_number ON round(event_id,number)')
            conn.execute('CREATE INDEX IF NOT EXISTS ix_school_event_user ON school(event_id,user_id)')
            conn.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return saved
