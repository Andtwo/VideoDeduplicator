"""停服后运行：VD_DATABASE_URL=... python -m web.migrate_analytics --sqlite ..."""
import argparse
import os
import sqlite3

from web.mysql_analytics import MySQLAnalytics


def migrate(source, target):
    """仅向空的目标表迁移；重复运行只校验，绝不覆盖生产记录。"""
    with sqlite3.connect(f'file:{source}?mode=ro', uri=True) as old, target.connect() as new:
        tables = {r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for legacy, table in [('visits','video_dedup_visits'), ('jobs','video_dedup_task_stats')]:
            source_table = table if table in tables else legacy
            cursor = old.execute(f'SELECT * FROM {source_table} ORDER BY id')
            columns = [c[0] for c in cursor.description]
            rows = cursor.fetchall()
            existing = [tuple(row) for row in new.execute(f'SELECT {",".join(columns)} FROM {table} ORDER BY id')]
            if existing:
                if existing != rows:
                    raise ValueError(f'{table} 已有不同数据，迁移已回滚，未覆盖目标数据')
            else:
                sql = f'INSERT INTO {table} ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})'
                for row in rows:
                    new.execute(sql,row)
            copied = [tuple(row) for row in new.execute(f'SELECT {",".join(columns)} FROM {table} ORDER BY id')]
            if copied != rows:
                raise ValueError(f'{table} 迁移校验失败')
            print(f'{table}: {len(rows)} 条，全部字段一致')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sqlite', required=True)
    args = parser.parse_args()
    migrate(args.sqlite, MySQLAnalytics(os.environ['VD_DATABASE_URL']))
