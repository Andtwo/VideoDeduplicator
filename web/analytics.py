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
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, title TEXT, strategy TEXT,
              created REAL, day TEXT, status TEXT, started REAL, ended REAL, downloads INTEGER DEFAULT 0, error TEXT DEFAULT '');
            CREATE INDEX IF NOT EXISTS jobs_day ON jobs(day);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
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
              status=excluded.status,started=excluded.started,ended=excluded.ended,error=excluded.error''',
              (task['task_id'], task.get('title',''),
               f"{task.get('strategy_name','')} v{task.get('strategy_version','')}", created,
               datetime.fromtimestamp(created,TZ).date().isoformat(),task['status'],
               task.get('started_at'),task.get('ended_at'),task.get('error_summary',''))) 

    def download(self, task_id):
        with self.connect() as db:
            db.execute('UPDATE jobs SET downloads=downloads+1 WHERE id=?',(task_id,))

    def report(self, start, end):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            visits = db.execute('SELECT count(*) pv,count(DISTINCT visitor) uv FROM visits WHERE day BETWEEN ? AND ?', (start,end)).fetchone()
            online = db.execute('SELECT count(DISTINCT visitor) FROM visits WHERE seen>?',(time.time()-90,)).fetchone()[0]
            jobs = [dict(r) for r in db.execute('SELECT * FROM jobs WHERE day BETWEEN ? AND ? ORDER BY created DESC',(start,end))]
            trend = [dict(r) for r in db.execute('SELECT day,count(*) pv,count(DISTINCT visitor) uv FROM visits WHERE day BETWEEN ? AND ? GROUP BY day ORDER BY day',(start,end))]
        done = sum(j['status']=='done' for j in jobs)
        failed = sum(j['status']=='error' for j in jobs)
        durations = sorted(j['ended']-j['started'] for j in jobs if j['status']=='done' and j['started'] and j['ended'])
        titles = {}
        strategies = {}
        errors = {}
        for j in jobs:
            if j['status']=='error':
                key=j['error'] or '历史任务未记录原因'
                errors[key]=errors.get(key,0)+1
            titles[j['title']] = titles.get(j['title'],0)+1
            strategies[j['strategy']] = strategies.get(j['strategy'],0)+1
        return dict(pv=visits['pv'],uv=visits['uv'],online=online,total=len(jobs),done=done,failed=failed,
            queued=sum(j['status']=='queued' for j in jobs),processing=sum(j['status']=='processing' for j in jobs),
            success_rate=done/(done+failed) if done+failed else None,
            download_rate=sum(j['status']=='done' and j['downloads']>0 for j in jobs)/done if done else None,
            downloads=sum(j['downloads'] for j in jobs),
            avg_seconds=sum(durations)/len(durations) if durations else None,
            p95_seconds=durations[min(len(durations)-1,int(len(durations)*.95))] if durations else None,
            titles=sorted(titles.items(),key=lambda x:-x[1])[:20],
            errors=sorted(errors.items(),key=lambda x:-x[1])[:20],
            strategies=sorted(strategies.items(),key=lambda x:-x[1]),trend=trend,jobs=jobs[:100])
