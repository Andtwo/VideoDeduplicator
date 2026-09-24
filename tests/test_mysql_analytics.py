"""使用独立测试库运行：VD_TEST_MYSQL_URL=mysql://... pytest ..."""
import os
import pytest

from web.analytics import Analytics


def test_mysql_matches_sqlite_and_migration(tmp_path):
    url = os.getenv('VD_TEST_MYSQL_URL')
    if not url:
        pytest.skip('需要独立 MySQL 测试库')
    from web.mysql_analytics import MySQLAnalytics
    from web.migrate_analytics import migrate
    mysql = MySQLAnalytics(url)
    source = tmp_path / 'stats.db'
    sqlite = Analytics(source)
    task = dict(task_id='one', title='中文🎬', created_at=1704038400, status='done',
                started_at=10, ended_at=30, strategy_name='测试策略', strategy_version=10)
    sqlite.visit('page','visitor');sqlite.task(task);sqlite.download('one')
    migrate(source,mysql)
    migrate(source,mysql)
    assert mysql.report('2000-01-01','2100-01-01') == sqlite.report('2000-01-01','2100-01-01')
    for store in (sqlite,mysql):
        store.task({**task,'status':'queued'})
        store.task({**task,'task_id':'two','status':'error','error_summary':'RuntimeError'})
        store.download('one')
        store.visit('second','visitor')
    # 时间字段在两次调用间不同，报表只返回汇总访问值。
    assert mysql.report('2000-01-01','2100-01-01') == sqlite.report('2000-01-01','2100-01-01')
    for store in (sqlite,mysql):
        store.remove('two')
    assert mysql.report('2000-01-01','2100-01-01')['total'] == 1
    sqlite.task({**task,'task_id':'not-migrated'})
    with pytest.raises(ValueError):
        migrate(source,mysql)
    assert mysql.report('2000-01-01','2100-01-01')['total'] == 1
