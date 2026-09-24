import pytest
from fastapi.testclient import TestClient
from web import app as module


@pytest.mark.parametrize('prefix', ['', '/video-deduplicator', '/tools/video'])
def test_pages_keep_proxy_prefix(prefix, monkeypatch):
    monkeypatch.setattr(module, 'ADMIN_TOKEN', 'test')
    client = TestClient(module.app)
    headers = {'X-Forwarded-Prefix': prefix}
    for path in ['/', '/admin/strategies']:
        response = client.get(path, headers=headers)
        assert response.status_code == 200
        assert f"const APP_BASE='{prefix}'" in response.text
        assert '__APP_BASE__' not in response.text
    assert f'href="{prefix}/"' in client.get('/admin/strategies', headers=headers).text
    assert client.get('/api/admin/strategies', headers=headers).status_code == 401


@pytest.mark.parametrize('prefix', ['//evil.example', '/bad\"path', '/a/../b'])
def test_reject_unsafe_prefix(prefix):
    assert TestClient(module.app).get('/', headers={'X-Forwarded-Prefix': prefix}).status_code == 400
