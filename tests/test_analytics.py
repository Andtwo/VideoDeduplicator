from web.analytics import Analytics


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


def test_empty_and_missing_duration(tmp_path):
    a=Analytics(tmp_path/'stats.db')
    r=a.report('2000-01-01','2100-01-01')
    assert r['success_rate'] is None and r['download_rate'] is None
    a.task({'task_id':'old','created_at':1704038400,'status':'done'})
    assert a.report('2000-01-01','2100-01-01')['avg_seconds'] is None
