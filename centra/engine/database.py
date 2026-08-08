"""SQLite database for multi-tenant scan storage."""
import aiosqlite
import json
import time
from pathlib import Path


class Database:
    def __init__(self, db_path: Path):
        self.path = str(db_path)
        self._db = None

    async def init(self):
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript('''
            CREATE TABLE IF NOT EXISTS companies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at REAL DEFAULT (strftime('%s','now'))
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                company_id TEXT NOT NULL,
                display_name TEXT DEFAULT '',
                role TEXT DEFAULT 'operator',
                created_at REAL DEFAULT (strftime('%s','now')),
                FOREIGN KEY (company_id) REFERENCES companies(id)
            );
            CREATE TABLE IF NOT EXISTS scans (
                id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                targets TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                progress REAL DEFAULT 0,
                plugin_ids TEXT DEFAULT '[]',
                total_plugins INTEGER DEFAULT 0,
                completed_plugins INTEGER DEFAULT 0,
                started_at REAL,
                finished_at REAL,
                created_at REAL DEFAULT (strftime('%s','now')),
                FOREIGN KEY (company_id) REFERENCES companies(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id TEXT NOT NULL,
                company_id TEXT NOT NULL,
                plugin_id INTEGER NOT NULL,
                plugin_name TEXT DEFAULT '',
                family TEXT DEFAULT '',
                cvss_score REAL DEFAULT 0,
                target TEXT DEFAULT '',
                port INTEGER DEFAULT 0,
                severity TEXT DEFAULT 'info',
                status TEXT DEFAULT 'fail',
                description TEXT DEFAULT '',
                solution TEXT DEFAULT '',
                reference_urls TEXT DEFAULT '[]',
                evidence TEXT DEFAULT '',
                created_at REAL DEFAULT (strftime('%s','now')),
                FOREIGN KEY (scan_id) REFERENCES scans(id),
                FOREIGN KEY (company_id) REFERENCES companies(id)
            );
            CREATE TABLE IF NOT EXISTS scan_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id TEXT NOT NULL,
                company_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                level TEXT DEFAULT 'info',
                plugin_id INTEGER,
                message TEXT NOT NULL,
                FOREIGN KEY (scan_id) REFERENCES scans(id)
            );
        ''')
        try:
            await self._db.execute('ALTER TABLE findings ADD COLUMN status TEXT DEFAULT "fail"')
        except Exception:
            pass
        # Add indexes for hot query paths
        await self._db.executescript('''
            CREATE INDEX IF NOT EXISTS idx_findings_scan_id ON findings(scan_id);
            CREATE INDEX IF NOT EXISTS idx_findings_company_id ON findings(company_id);
            CREATE INDEX IF NOT EXISTS idx_scan_logs_scan_id ON scan_logs(scan_id);
            CREATE INDEX IF NOT EXISTS idx_scans_company_status ON scans(company_id, status, created_at);
        ''')
        # Use WAL + NORMAL sync for much better write throughput
        await self._db.execute('PRAGMA journal_mode=WAL')
        await self._db.execute('PRAGMA synchronous=NORMAL')
        await self._db.commit()

    async def ensure_company(self, cid: str, name: str):
        await self._db.execute(
            'INSERT OR IGNORE INTO companies (id, name) VALUES (?, ?)', (cid, name)
        )
        await self._db.commit()

    async def get_user(self, username: str) -> dict | None:
        async with self._db.execute(
            'SELECT * FROM users WHERE username = ?', (username,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def get_user_by_id(self, user_id: int) -> dict | None:
        async with self._db.execute(
            'SELECT id, username, company_id, display_name, role FROM users WHERE id = ?',
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def create_user(self, username: str, password_hash: str, company_id: str,
                          display_name: str = '', role: str = 'operator') -> int:
        cursor = await self._db.execute(
            'INSERT INTO users (username, password_hash, company_id, display_name, role) VALUES (?,?,?,?,?)',
            (username, password_hash, company_id, display_name, role)
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_companies(self) -> list[dict]:
        async with self._db.execute('SELECT * FROM companies ORDER BY name') as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_targets(self, company_id: str) -> list[dict]:
        from engine import COMPANY_TARGETS
        return COMPANY_TARGETS.get(company_id, [])

    async def create_scan(self, company_id: str, user_id: int, targets: list[str]) -> str:
        import uuid
        scan_id = 'HS-' + uuid.uuid4().hex[:12].upper()
        await self._db.execute(
            '''INSERT INTO scans (id, company_id, user_id, targets, status, created_at)
               VALUES (?, ?, ?, ?, 'queued', ?)''',
            (scan_id, company_id, user_id, json.dumps(targets), time.time())
        )
        await self._db.commit()
        return scan_id

    async def update_scan(self, scan_id: str, **kwargs):
        sets = ', '.join(f'{k} = ?' for k in kwargs)
        vals = list(kwargs.values()) + [scan_id]
        await self._db.execute(f'UPDATE scans SET {sets} WHERE id = ?', vals)
        await self._db.commit()

    async def get_scan(self, scan_id: str, company_id: str) -> dict | None:
        async with self._db.execute(
            'SELECT * FROM scans WHERE id = ? AND company_id = ?',
            (scan_id, company_id)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def get_scans(self, company_id: str, limit: int = 50) -> list[dict]:
        async with self._db.execute(
            'SELECT * FROM scans WHERE company_id = ? ORDER BY created_at DESC LIMIT ?',
            (company_id, limit)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def delete_scan(self, scan_id: str, company_id: str):
        await self._db.execute(
            'DELETE FROM findings WHERE scan_id = ? AND company_id = ?',
            (scan_id, company_id)
        )
        await self._db.execute(
            'DELETE FROM scan_logs WHERE scan_id = ? AND company_id = ?',
            (scan_id, company_id)
        )
        await self._db.execute(
            'DELETE FROM scans WHERE id = ? AND company_id = ?',
            (scan_id, company_id)
        )
        await self._db.commit()

    async def add_finding(self, scan_id: str, company_id: str, plugin_id: int,
                          plugin_name: str, family: str, cvss: float, target: str,
                          port: int, severity: str, description: str, solution: str,
                          references: list[str], evidence: str, status: str = 'fail'):
        await self._db.execute(
            '''INSERT INTO findings
               (scan_id, company_id, plugin_id, plugin_name, family, cvss_score,
                target, port, severity, status, description, solution, reference_urls, evidence)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (scan_id, company_id, plugin_id, plugin_name, family, cvss,
             target, port, severity, status, description, solution, json.dumps(references), evidence)
        )
        await self._db.commit()

    async def add_findings_batch(self, findings: list[tuple]):
        """Insert multiple findings in a single transaction. Each tuple matches add_finding args."""
        if not findings:
            return
        await self._db.executemany(
            '''INSERT INTO findings
               (scan_id, company_id, plugin_id, plugin_name, family, cvss_score,
                target, port, severity, status, description, solution, reference_urls, evidence)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            findings
        )
        await self._db.commit()

    async def get_findings(self, scan_id: str) -> list[dict]:
        async with self._db.execute(
            'SELECT * FROM findings WHERE scan_id = ? ORDER BY cvss_score DESC',
            (scan_id,)
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
            for r in rows:
                r['reference_urls'] = json.loads(r.get('reference_urls', '[]'))
            return rows

    async def add_log(self, scan_id: str, company_id: str, level: str,
                      plugin_id: int | None, message: str):
        await self._db.execute(
            'INSERT INTO scan_logs (scan_id, company_id, timestamp, level, plugin_id, message) VALUES (?,?,?,?,?,?)',
            (scan_id, company_id, time.time(), level, plugin_id, message)
        )
        await self._db.commit()

    async def get_logs(self, scan_id: str) -> list[dict]:
        async with self._db.execute(
            'SELECT * FROM scan_logs WHERE scan_id = ? ORDER BY timestamp ASC',
            (scan_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_stats(self, company_id: str) -> dict:
        async with self._db.execute(
            'SELECT COUNT(*) as total, SUM(CASE WHEN status="completed" THEN 1 ELSE 0 END) as completed FROM scans WHERE company_id = ?',
            (company_id,)
        ) as cur:
            row = await cur.fetchone()
            scan_stats = dict(row) if row else {'total': 0, 'completed': 0}

        async with self._db.execute(
            'SELECT COUNT(*) as total, SUM(CASE WHEN severity="critical" THEN 1 ELSE 0 END) as critical, SUM(CASE WHEN severity="high" THEN 1 ELSE 0 END) as high FROM findings WHERE company_id = ?',
            (company_id,)
        ) as cur:
            row = await cur.fetchone()
            finding_stats = dict(row) if row else {'total': 0, 'critical': 0, 'high': 0}

        return {**scan_stats, **finding_stats}
