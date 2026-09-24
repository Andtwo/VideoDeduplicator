import sqlite3

import pytest

from web.analytics import Analytics


def test_legacy_migration_preserves_data(tmp_path):
    path = tmp_path / 'stats.db'
    with sqlite3.connect(path) as db:
        db.executescript('''
            CREATE TABLE visits(id TEXT PRIMARY KEY, visitor TEXT, day TEXT, seen REAL);
            CREATE INDEX visits_day ON visits(day);
            CREATE INDEX visits_seen ON visits(seen, visitor);
            INSERT INTO visits VALUES('page:2024-01-01','visitor','2024-01-01',1704038400);
            CREATE TABLE jobs(id TEXT PRIMARY KEY, title TEXT, strategy TEXT,
                created REAL, day TEXT, status TEXT, started REAL, ended REAL,
                downloads INTEGER DEFAULT 0, error TEXT DEFAULT '');
            CREATE INDEX jobs_day ON jobs(day);
            INSERT INTO jobs VALUES('one','测试','策略 v1',1704038400,'2024-01-01','done',10,30,7,'');
        ''')
    a = Analytics(path)
    expected = a.report('2024-01-01', '2024-01-01')
    assert (expected['pv'], expected['uv'], expected['done'], expected['downloads']) == (1, 1, 1, 7)
    assert expected['avg_seconds'] == 20
    assert expected['jobs'][0]['title'] == '测试'
    assert Analytics(path).report('2024-01-01', '2024-01-01') == expected
    a.download('one')
    assert a.report('2024-01-01', '2024-01-01')['downloads'] == 8
    with a.connect() as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {'video_dedup_visits', 'video_dedup_task_stats'}


def test_conflicting_tables_roll_back_migration(tmp_path):
    path = tmp_path / 'stats.db'
    with sqlite3.connect(path) as db:
        db.executescript('CREATE TABLE visits(id TEXT); CREATE TABLE jobs(id TEXT); '
                         'CREATE TABLE video_dedup_task_stats(id TEXT);')
    with pytest.raises(sqlite3.IntegrityError):
        Analytics(path)
    with sqlite3.connect(path) as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {'visits', 'jobs', 'video_dedup_task_stats'}


def test_visits_tasks_and_downloads(tmp_path):
    a=Analytics(tmp_path/'stats.db')
    a.visit('p1','v1');a.visit('p1','v1');a.visit('p2','v1');a.visit('p3','v2')
    task={'task_id':'one','created_at':1704038400,'status':'done','title':'测试','started_at':10,'ended_at':30}
    a.task(task);a.download('one');a.task(task)
    a.task({**task,'task_id':'two','status':'error','error_summary':'RuntimeError'})
    r=a.report('2000-01-01','2100-01-01')
    assert (r['pv'],r['uv'],r['online'])==(3,2,2)
    assert r['success_rate']==.5 and r['download_rate']==1
    assert r['downloads']==1 and r['avg_seconds']==20
    assert r['errors']==[('RuntimeError',1)]
    assert Analytics(tmp_path/'stats.db').report('2000-01-01','2100-01-01')['total']==2


def test_percentile_limits_and_index(tmp_path):
    a=Analytics(tmp_path/'stats.db')
    for i in range(120):
        a.task({'task_id':str(i),'created_at':1704038400,'status':'done',
                'started_at':100,'ended_at':101+i})
    r=a.report('2000-01-01','2100-01-01')
    assert r['total']==120 and len(r['jobs'])==100
    assert r['p95_seconds']==114
    with a.connect() as db:
        plan=db.execute('EXPLAIN QUERY PLAN SELECT count(DISTINCT visitor) FROM video_dedup_visits WHERE seen>0').fetchall()
        assert any('video_dedup_visits_seen' in str(row) for row in plan)
    # 延迟补录的旧状态不能覆盖已完成状态。
    a.task({'task_id':'0','created_at':1704038400,'status':'queued'})
    assert a.report('2000-01-01','2100-01-01')['done']==120


def test_empty_and_missing_duration(tmp_path):
    a=Analytics(tmp_path/'stats.db')
    r=a.report('2000-01-01','2100-01-01')
    assert r['success_rate'] is None and r['download_rate'] is None
    a.task({'task_id':'old','created_at':1704038400,'status':'done'})
    assert a.report('2000-01-01','2100-01-01')['avg_seconds'] is None
