"""统计数据库故障不能中断业务。"""
import sqlite3
from unittest.mock import Mock
from web import app as m
from fastapi.testclient import TestClient


def test_task_and_download_survive_statistics_failure(tmp_path, monkeypatch):
    broken=Mock()
    broken.task.side_effect=sqlite3.OperationalError('database is locked')
    broken.download.side_effect=sqlite3.OperationalError('database is locked')
    monkeypatch.setattr(m,'ANALYTICS',broken)
    monkeypatch.setattr(m,'UPLOADS',tmp_path)
    output=tmp_path/'out.mp4';output.write_bytes(b'video')
    task={'task_id':'test','created_at':1,'status':'queued','download_name':'test.mp4','output':str(output)}
    monkeypatch.setattr(m,'_tasks',{'test':task})
    m._update_task('test',status='processing')
    m._update_task('test',status='done')
    assert task['status']=='done'
    assert (tmp_path/'test'/'task.json').exists()
    assert m.download('test').path==output


def test_usage_survives_failure_and_report_is_unavailable(monkeypatch):
    broken=Mock()
    broken.visit.side_effect=sqlite3.OperationalError('database is locked')
    broken.report.side_effect=sqlite3.OperationalError('database is locked')
    monkeypatch.setattr(m,'ANALYTICS',broken)
    monkeypatch.setattr(m,'ADMIN_TOKEN','test')
    c=TestClient(m.app)
    assert c.post('/api/usage',json={'page':'a'*32,'visitor':'b'*32}).status_code==204
    assert c.get('/api/admin/statistics?start=2026-01-01&end=2026-01-02',headers={'X-Admin-Token':'test'}).status_code==503
