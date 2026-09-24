"""MySQL 统计存储；复用 Analytics 的只读聚合口径。"""
from contextlib import contextmanager
from datetime import datetime
import time
from urllib.parse import unquote, urlsplit

import pymysql

from web.analytics import Analytics, TZ


class Row(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)

    def __iter__(self):
        return iter(self.values())


class Connection:
    """将内部固定 SQL 的问号参数适配至 PyMySQL，保持参数绑定。"""
    row_factory = None

    def __init__(self, db):
        self.db = db

    def execute(self, sql, args=()):
        cursor = self.db.cursor()
        try:
            cursor.execute(sql.replace('?', '%s'), args)
            rows = [Row(row) for row in cursor.fetchall()] if cursor.description else []
            return Result(rows)
        finally:
            cursor.close()


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows

    def __iter__(self):
        return iter(self.rows)


class MySQLAnalytics(Analytics):
    def __init__(self, url):
        parsed = urlsplit(url)
        if parsed.scheme not in ('mysql', 'mysql+pymysql') or not parsed.hostname or not parsed.path.strip('/'):
            raise ValueError('VD_DATABASE_URL 必须是有效的 MySQL 数据库连接地址')
        self.options = dict(host=parsed.hostname, port=parsed.port or 3306,
                            user=unquote(parsed.username or ''), password=unquote(parsed.password or ''),
                            database=unquote(parsed.path.lstrip('/')), charset='utf8mb4',
                            connect_timeout=3, read_timeout=10, write_timeout=10,
                            cursorclass=pymysql.cursors.DictCursor)
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS video_dedup_visits (
                id VARCHAR(80) PRIMARY KEY, visitor VARCHAR(64) NOT NULL,
                day CHAR(10) NOT NULL, seen DOUBLE NOT NULL,
                INDEX video_dedup_visits_day(day), INDEX video_dedup_visits_seen(seen,visitor)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin''')
            db.execute('''CREATE TABLE IF NOT EXISTS video_dedup_task_stats (
                id VARCHAR(64) PRIMARY KEY, title VARCHAR(255), strategy VARCHAR(512),
                created DOUBLE, day CHAR(10), status VARCHAR(32), started DOUBLE NULL,
                ended DOUBLE NULL, downloads BIGINT NOT NULL DEFAULT 0, error VARCHAR(255) DEFAULT '',
                INDEX video_dedup_task_stats_day(day)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin''')

    @contextmanager
    def connect(self):
        db = pymysql.connect(**self.options)
        try:
            with db.cursor() as cursor:
                cursor.execute("SET time_zone = '+08:00'")
                cursor.execute('SET SESSION innodb_lock_wait_timeout = 1')
            yield Connection(db)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def visit(self, page, visitor):
        now = time.time()
        day = datetime.fromtimestamp(now, TZ).date().isoformat()
        with self.connect() as db:
            db.execute('''INSERT INTO video_dedup_visits(id,visitor,day,seen) VALUES(?,?,?,?)
                ON DUPLICATE KEY UPDATE seen=VALUES(seen)''', (page+':'+day, visitor, day, now))

    def task(self, task):
        created = task['created_at']
        allowed = "((status NOT IN ('done','error') OR VALUES(status) IN ('done','error')) AND NOT (status='processing' AND VALUES(status)='queued'))"
        # status 最后赋值，避免 MySQL 左到右更新影响后续条件。
        updates = ','.join(f'{key}=IF({allowed},VALUES({key}),{key})' for key in ('started','ended','error','status'))
        with self.connect() as db:
            db.execute('''INSERT INTO video_dedup_task_stats
                (id,title,strategy,created,day,status,started,ended,error) VALUES(?,?,?,?,?,?,?,?,?)
                ON DUPLICATE KEY UPDATE '''+updates,
                (task['task_id'],task.get('title',''),
                 f"{task.get('strategy_name','')} v{task.get('strategy_version','')}",created,
                 datetime.fromtimestamp(created,TZ).date().isoformat(),task['status'],
                 task.get('started_at'),task.get('ended_at'),task.get('error_summary','')))
