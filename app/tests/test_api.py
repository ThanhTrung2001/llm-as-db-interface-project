"""Kiểm thử chức năng qua API theo từng use case và vai trò."""
import pytest
from fastapi.testclient import TestClient

from app.backend import llm
from app.backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    """Không bao giờ gọi model thật trong test; ca nào cần thì tự giả lập."""
    def offline(*a, **k):
        raise llm.LLMError('test: không gọi model thật')
    monkeypatch.setattr(llm, 'complete', offline)


def login(username, password):
    r = client.post('/api/login', json={'username': username, 'password': password})
    assert r.status_code == 200, r.text
    return {'Authorization': 'Bearer ' + r.json()['token']}


@pytest.fixture(scope='module')
def admin():
    return login('admin', 'admin123')


@pytest.fixture(scope='module')
def board():
    return login('thuquy', 'thuquy123')


@pytest.fixture(scope='module')
def member():
    return login('thanhvien', 'thanhvien123')


def run_id(headers, model='GPT-3.5-Turbo', config='evidence'):
    runs = client.get('/api/benchmark/runs', headers=headers).json()
    return next(r['id'] for r in runs if r['model_name'] == model and r['config'] == config)


def finance_question(headers):
    qs = client.get('/api/dev-questions', headers=headers).json()
    return next(q['id'] for q in qs if 'expense' in q['question'].lower() or 'spent' in q['question'].lower())


# ---- UC01 ----

def test_login_wrong_password():
    assert client.post('/api/login', json={'username': 'admin', 'password': 'x'}).status_code == 401


def test_requires_login():
    assert client.get('/api/history').status_code == 401


# ---- UC02 (phát lại) ----

def test_replay_board_returns_result_and_gold(board, conn):
    rid = run_id(board)
    qid = client.get('/api/dev-questions', headers=board).json()[0]['id']
    r = client.post('/api/ask', headers=board, json={'mode': 'replay', 'run_id': rid, 'dev_question_id': qid})
    body = r.json()
    assert r.status_code == 200 and body['status'] in ('EXECUTED', 'EXEC_ERROR')
    expected = conn.execute('SELECT is_correct FROM benchmark_item WHERE run_id = ? AND question_id = ?',
                            (rid, qid)).fetchone()[0]
    assert body['is_correct'] == expected and body['gold_sql']


def test_member_finance_question_rejected_and_logged(member, conn):
    qid = finance_question(member)
    r = client.post('/api/ask', headers=member,
                    json={'mode': 'replay', 'run_id': run_id(member), 'dev_question_id': qid}).json()
    assert r['status'] == 'REJECTED_PERMISSION'
    row = conn.execute('SELECT status FROM query_log WHERE id = ?', (r['log_id'],)).fetchone()
    assert row['status'] == 'REJECTED_PERMISSION'  # BR04


def test_live_uses_glossary_and_role_schema(member, monkeypatch):
    seen = {}

    def fake_generate(model, prompt_text, timeout_s=120):
        seen['prompt'] = prompt_text
        return "SELECT COUNT(*) FROM event WHERE type = 'Meeting'"

    def fake_complete(model, prompt_text, **kw):
        seen['answer_prompt'] = prompt_text
        return 'Câu lạc bộ đã tổ chức 18 buổi họp.'

    monkeypatch.setattr(llm, 'generate_sql', fake_generate)
    monkeypatch.setattr(llm, 'complete', fake_complete)
    r = client.post('/api/ask', headers=member,
                    json={'mode': 'live', 'model_id': 1, 'question': 'How many meeting events are there?'}).json()
    assert r['status'] == 'EXECUTED' and r['rows'][0][0] > 0
    assert [t['term'] for t in r['glossary_used']] == ['meeting']
    assert "event.type = 'Meeting'" in seen['prompt']
    assert 'expense' not in seen['prompt']  # thành viên không thấy bảng tài chính
    # UC02f: câu trả lời do model diễn giải, dựa trên đúng kết quả đã thực thi
    assert r['answer'] == 'Câu lạc bộ đã tổ chức 18 buổi họp.' and r['answer_source'] == 'llm'
    assert str(r['rows'][0][0]) in seen['answer_prompt']


def test_live_answer_falls_back_to_template(member, monkeypatch):
    monkeypatch.setattr(llm, 'generate_sql', lambda *a, **k: "SELECT COUNT(*) FROM event WHERE type = 'Meeting'")
    r = client.post('/api/ask', headers=member,
                    json={'mode': 'live', 'model_id': 1, 'question': 'How many meetings?'}).json()
    assert r['status'] == 'EXECUTED' and r['answer_source'] == 'template'
    assert r['answer'] == f"Kết quả: {r['rows'][0][0]}."


def test_replay_answer_is_offline_and_logged(board, conn):
    qid = client.get('/api/dev-questions', headers=board).json()[0]['id']
    r = client.post('/api/ask', headers=board,
                    json={'mode': 'replay', 'run_id': run_id(board), 'dev_question_id': qid}).json()
    if r['status'] == 'EXECUTED':
        assert r['answer'] and r['answer_source'] == 'template'
        logged = conn.execute('SELECT answer FROM query_log WHERE id = ?', (r['log_id'],)).fetchone()[0]
        assert logged == r['answer']


def test_live_llm_failure_logged(member, monkeypatch):
    def boom(*a, **k):
        raise llm.LLMError('Lỗi gọi model: connection refused')

    monkeypatch.setattr(llm, 'generate_sql', boom)
    r = client.post('/api/ask', headers=member, json={'mode': 'live', 'model_id': 2, 'question': 'x?'}).json()
    assert r['status'] == 'FAILED_GENERATION' and r['log_id']


def test_live_unsafe_sql_rejected(admin, monkeypatch):
    monkeypatch.setattr(llm, 'generate_sql', lambda *a, **k: 'DELETE FROM member')
    r = client.post('/api/ask', headers=admin, json={'mode': 'live', 'model_id': 1, 'question': 'xoá hết'}).json()
    assert r['status'] == 'REJECTED_UNSAFE'


# ---- UC03, UC04, UC05, UC10 ----

def test_history_feedback_export(board):
    rid = run_id(board)
    qid = client.get('/api/dev-questions', headers=board).json()[1]['id']
    log_id = client.post('/api/ask', headers=board,
                         json={'mode': 'replay', 'run_id': rid, 'dev_question_id': qid}).json()['log_id']
    hist = client.get('/api/history', headers=board).json()
    assert hist[0]['id'] == log_id
    assert client.post('/api/feedback', headers=board,
                       json={'query_log_id': log_id, 'rating': 1, 'comment': 'ok'}).status_code == 200
    if hist[0]['status'] == 'EXECUTED':
        r = client.get(f'/api/export/{log_id}', headers=board)
        assert r.status_code == 200 and r.headers['content-type'].startswith('text/csv')


def test_member_cannot_export_or_see_logs(member):
    assert client.get('/api/export/1', headers=member).status_code == 403
    assert client.get('/api/logs', headers=member).status_code == 403


def test_admin_logs_stats(admin):
    body = client.get('/api/logs', headers=admin).json()
    assert body['rows'] and {s['status'] for s in body['stats']} >= {'REJECTED_PERMISSION'}


# ---- UC06, BR05 ----

def test_glossary_crud_admin_only(admin, member):
    assert client.post('/api/glossary', headers=member,
                       json={'term': 'x', 'definition': 'y'}).status_code == 403
    new_id = client.post('/api/glossary', headers=admin,
                         json={'term': 'sự kiện mở', 'definition': "event.status = 'Open'"}).json()['id']
    assert client.post('/api/glossary', headers=admin,
                       json={'term': 'Sự kiện mở', 'definition': 'dup'}).status_code == 409
    assert client.put(f'/api/glossary/{new_id}', headers=admin,
                      json={'term': 'sự kiện mở', 'definition': "event.status = 'Open'",
                            'is_active': False}).status_code == 200
    assert client.delete(f'/api/glossary/{new_id}', headers=admin).status_code == 200


# ---- UC07, UC08, UC09, UC11 ----

def test_model_config_admin_only(admin, member):
    body = {'model_tag': 'qwen2.5-coder:7b', 'base_url': 'http://localhost:11434/v1', 'is_active': True}
    assert client.put('/api/models/4', headers=member, json=body).status_code == 403
    assert client.put('/api/models/4', headers=admin, json=body).status_code == 200


def test_benchmark_import_validates(admin):
    assert client.post('/api/benchmark/import', headers=admin, json={'x': 1}).status_code == 422
    bad = {'questions': [], 'runs': [{'model': 'Không có', 'config': 'evidence', 'source': 's',
                                      'total': 1, 'items': []}]}
    assert client.post('/api/benchmark/import', headers=admin, json=bad).status_code == 422


def test_benchmark_summary(board, member):
    s = client.get('/api/benchmark/summary', headers=board).json()
    assert len(s) == 12 and all(set(r['levels']) == {'simple', 'moderate', 'challenging'} for r in s)
    assert client.get('/api/benchmark/summary', headers=member).status_code == 403


def test_user_management(admin, member):
    assert client.get('/api/users', headers=member).status_code == 403
    r = client.post('/api/users', headers=admin,
                    json={'username': 'banchunhiem', 'full_name': 'BCN', 'role': 'board', 'password': 'bcn123'})
    assert r.status_code == 200
    login('banchunhiem', 'bcn123')
    me = client.get('/api/me', headers=admin).json()
    assert client.put(f"/api/users/{me['id']}", headers=admin,
                      json={'username': 'admin', 'full_name': 'x', 'role': 'member'}).status_code == 422
