"""持久化匿名使用统计；不保存 IP 或设备指纹。"""
from contextlib import contextmanager
import sqlite3
import time
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=8))


class Analytics:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS visits(id TEXT PRIMARY KEY, visitor TEXT, day TEXT, seen REAL);
            CREATE INDEX IF NOT EXISTS visits_day ON visits(day);
            CREATE INDEX IF NOT EXISTS visits_seen ON visits(seen, visitor);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, title TEXT, strategy TEXT,
              created REAL, day TEXT, status TEXT, started REAL, ended REAL, downloads INTEGER DEFAULT 0, error TEXT DEFAULT '');
            CREATE INDEX IF NOT EXISTS jobs_day ON jobs(day);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=0.2)
        try:
            with db:
                yield db
        finally:
            db.close()

    def visit(self, page, visitor):
        now = time.time()
        day = datetime.fromtimestamp(now, TZ).date().isoformat()
        with self.connect() as db:
            db.execute('INSERT INTO visits VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET seen=excluded.seen',
                       (page + ':' + day, visitor, day, now))

    def task(self, task):
        created = task['created_at']
        with self.connect() as db:
            db.execute('''INSERT INTO jobs(id,title,strategy,created,day,status,started,ended,error)
              VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
              status=excluded.status,started=excluded.started,ended=excluded.ended,error=excluded.error
              WHERE (jobs.status NOT IN ('done','error') OR excluded.status IN ('done','error'))
              AND NOT (jobs.status='processing' AND excluded.status='queued')''',
              (task['task_id'], task.get('title',''),
               f"{task.get('strategy_name','')} v{task.get('strategy_version','')}", created,
               datetime.fromtimestamp(created,TZ).date().isoformat(),task['status'],
               task.get('started_at'),task.get('ended_at'),task.get('error_summary',''))) 

    def remove(self, task_id):
        with self.connect() as db:
            db.execute('DELETE FROM jobs WHERE id=?', (task_id,))

    def download(self, task_id):
        with self.connect() as db:
            db.execute('UPDATE jobs SET downloads=downloads+1 WHERE id=?',(task_id,))

    def report(self, start, end):
        import math
        args = (start, end)
        where = 'day BETWEEN ? AND ?'
        duration_where = where + " AND status='done' AND started IS NOT NULL AND ended>=started"
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN')  # 同一快照，避免并发更新造成分子分母不一致。
            visits = db.execute(f'SELECT count(*) pv,count(DISTINCT visitor) uv FROM visits WHERE {where}', args).fetchone()
            online = db.execute('SELECT count(DISTINCT visitor) FROM visits WHERE seen>?', (time.time()-90,)).fetchone()[0]
            summary = dict(db.execute(f'''SELECT count(*) total,
                coalesce(sum(status='done'),0) done, coalesce(sum(status='error'),0) failed,
                coalesce(sum(status='queued'),0) queued, coalesce(sum(status='processing'),0) processing,
                coalesce(sum(downloads),0) downloads,
                coalesce(sum(status='done' AND downloads>0),0) downloaded
                FROM jobs WHERE {where}''', args).fetchone())
            duration = db.execute(f'SELECT count(*),avg(ended-started) FROM jobs WHERE {duration_where}', args).fetchone()
            p95 = None
            if duration[0]:
                p95 = db.execute(f'SELECT ended-started FROM jobs WHERE {duration_where} ORDER BY ended-started LIMIT 1 OFFSET ?',
                                 (*args, math.ceil(duration[0]*.95)-1)).fetchone()[0]
            jobs = [dict(r) for r in db.execute(f'SELECT * FROM jobs WHERE {where} ORDER BY created DESC LIMIT 100', args)]
            trend = [dict(r) for r in db.execute(f'SELECT day,count(*) pv,count(DISTINCT visitor) uv FROM visits WHERE {where} GROUP BY day ORDER BY day', args)]
            def groups(column, extra='', limit=20):
                return [tuple(r) for r in db.execute(f'SELECT {column},count(*) n FROM jobs WHERE {where} {extra} GROUP BY 1 ORDER BY n DESC,1 LIMIT ?', (*args,limit))]
            titles = groups('title')
            strategies = groups('strategy', limit=100)
            errors = groups("coalesce(nullif(error,''),'历史任务未记录原因')", "AND status='error'")
        done, failed = summary['done'], summary['failed']
        downloaded = summary.pop('downloaded')
        return dict(**summary, pv=visits['pv'], uv=visits['uv'], online=online,
                    success_rate=done/(done+failed) if done+failed else None,
                    download_rate=downloaded/done if done else None,
                    avg_seconds=duration[1], p95_seconds=p95,
                    titles=titles, strategies=strategies, errors=errors, trend=trend, jobs=jobs)
