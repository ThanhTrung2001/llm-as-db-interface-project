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
def president():
    return login('chunhiem', 'chunhiem123')


@pytest.fixture(scope='module')
def treasurer():
    return login('thuquy', 'thuquy123')


@pytest.fixture(scope='module')
def event_team():
    return login('bansukien', 'bansukien123')


@pytest.fixture(scope='module')
def admin():
    return login('admin', 'admin123')


def fake_sql(monkeypatch, sql, seen=None):
    def gen(model, prompt_text, timeout_s=120):
        if seen is not None:
            seen['prompt'] = prompt_text
        return sql
    monkeypatch.setattr(llm, 'generate_sql', gen)


def open_budget(headers, min_remaining=0):
    return next(b for b in client.get('/api/budgets', headers=headers).json()
                if b['event_status'] != 'Closed' and b['remaining'] >= min_remaining)

# ---- UC01 Đăng nhập, đổi mật khẩu ----


def test_login_wrong_password():
    assert client.post('/api/login', json={'username': 'admin', 'password': 'x'}).status_code == 401


def test_requires_login():
    assert client.get('/api/history').status_code == 401
    assert client.get('/api/members').status_code == 401


def test_me_returns_permissions(treasurer):
    me = client.get('/api/me', headers=treasurer).json()
    assert me['role'] == 'treasurer' and 'finance.write' in me['permissions'] and 'pii.read' not in me['permissions']


def test_change_password(admin):
    client.post('/api/users', headers=admin, json={'username': 'doimk', 'full_name': 'Đổi MK', 'role': 'event',
                                                   'password': 'cu1234'})
    h = login('doimk', 'cu1234')
    assert client.post('/api/me/password', headers=h,
                       json={'old_password': 'sai', 'new_password': 'moi1234'}).status_code == 422
    assert client.post('/api/me/password', headers=h,
                       json={'old_password': 'cu1234', 'new_password': 'moi1234'}).status_code == 200
    login('doimk', 'moi1234')

# ---- UC02 Hỏi đáp ----


def test_ask_uses_glossary_and_role_schema(event_team, monkeypatch):
    seen = {}
    fake_sql(monkeypatch, "SELECT COUNT(*) FROM event WHERE type = 'Meeting'", seen)
    r = client.post('/api/ask', headers=event_team, json={'question': 'How many meetings were held?'}).json()
    assert r['status'] == 'EXECUTED' and r['rows'][0][0] > 0
    assert [t['term'] for t in r['glossary_used']] == ['meeting']
    assert "-- External Knowledge: meeting refers to event.type = 'Meeting'" in seen['prompt']
    assert 'expense' not in seen['prompt'] and 'email' not in seen['prompt']  # ban sự kiện không thấy
    assert r['answer'] == f"Result: {r['rows'][0][0]}." and r['answer_source'] == 'template'


def test_ask_with_external_knowledge_and_sample(president, monkeypatch, conn):
    """Tri thức ngoài (evidence) đi vào dòng External Knowledge nguyên văn, trước các thuật ngữ từ điển."""
    seen = {}
    fake_sql(monkeypatch, "SELECT COUNT(*) FROM event WHERE type = 'Meeting'", seen)
    samples = client.get('/api/sample-questions', headers=president).json()
    assert len(samples) == 158 and sum(1 for x in samples if x['evidence']) == 146
    q = next(x for x in samples if x['evidence'])
    r = client.post('/api/ask', headers=president,
                    json={'question': q['question'], 'evidence': q['evidence'], 'sample_id': q['id']}).json()
    assert f"-- External Knowledge: {q['evidence']}" in seen['prompt']
    assert r['knowledge'].startswith(q['evidence']) and r['sample_id'] == q['id']
    row = conn.execute('SELECT evidence, sample_id FROM query_log WHERE id = ?', (r['log_id'],)).fetchone()
    assert tuple(row) == (q['evidence'], q['id'])
    # tự nhập tri thức + câu chứa thuật ngữ → cả hai được ghép
    r = client.post('/api/ask', headers=president, json={'question': 'How many meetings?',
                                                         'evidence': "2020 refers to event_date LIKE '2020%'"}).json()
    assert r['knowledge'] == "2020 refers to event_date LIKE '2020%'; meeting refers to event.type = 'Meeting'"
    # không có tri thức → không có dòng External Knowledge
    client.post('/api/ask', headers=president, json={'question': 'How many events are there?', 'evidence': '  '})
    assert 'External Knowledge' not in seen['prompt']


def test_ask_answer_from_llm(president, monkeypatch):
    fake_sql(monkeypatch, 'SELECT COUNT(*) FROM member')
    monkeypatch.setattr(llm, 'complete', lambda model, p, **kw: 'The club has 33 members.')
    r = client.post('/api/ask', headers=president, json={'question': 'How many people are in the club?'}).json()
    assert r['answer'] == 'The club has 33 members.' and r['answer_source'] == 'llm'


def test_ask_finance_rejected_for_event_team_and_logged(event_team, monkeypatch, conn):
    fake_sql(monkeypatch, 'SELECT SUM(cost) FROM expense')
    r = client.post('/api/ask', headers=event_team, json={'question': 'Tổng chi là bao nhiêu?'}).json()
    assert r['status'] == 'REJECTED_PERMISSION'
    assert conn.execute('SELECT status FROM query_log WHERE id = ?', (r['log_id'],)).fetchone()[0] \
        == 'REJECTED_PERMISSION'  # BR04


def test_ask_unsafe_sql_rejected(president, monkeypatch):
    fake_sql(monkeypatch, 'DELETE FROM member')
    r = client.post('/api/ask', headers=president, json={'question': 'xoá hết thành viên'}).json()
    assert r['status'] == 'REJECTED_UNSAFE'


def test_ask_llm_failure_logged(president, monkeypatch):
    def boom(*a, **k):
        raise llm.LLMError('Lỗi gọi model: connection refused')
    monkeypatch.setattr(llm, 'generate_sql', boom)
    r = client.post('/api/ask', headers=president, json={'question': 'abc?'}).json()
    assert r['status'] == 'FAILED_GENERATION' and r['log_id']


def test_ask_inactive_model_rejected(president):
    assert client.post('/api/ask', headers=president, json={'question': 'abc?', 'model_id': 999}).status_code == 422

# ---- UC03, UC04, UC05, UC10 ----


def test_history_feedback_export(treasurer, monkeypatch):
    fake_sql(monkeypatch, 'SELECT category, SUM(spent) FROM budget GROUP BY category')
    log_id = client.post('/api/ask', headers=treasurer, json={'question': 'Chi theo hạng mục?'}).json()['log_id']
    hist = client.get('/api/history', headers=treasurer).json()
    assert hist[0]['id'] == log_id
    assert client.post('/api/feedback', headers=treasurer, json={'query_log_id': log_id, 'rating': 1}).status_code == 200
    assert client.get('/api/history', headers=treasurer).json()[0]['rating'] == 1
    r = client.get(f'/api/export/{log_id}', headers=treasurer)
    assert r.status_code == 200 and r.headers['content-type'].startswith('text/csv')


def test_cannot_export_or_rate_others_question(treasurer, president, monkeypatch):
    fake_sql(monkeypatch, 'SELECT COUNT(*) FROM member')
    log_id = client.post('/api/ask', headers=treasurer, json={'question': 'Bao nhiêu người?'}).json()['log_id']
    assert client.get(f'/api/export/{log_id}', headers=president).status_code == 404
    assert client.post('/api/feedback', headers=president,
                       json={'query_log_id': log_id, 'rating': 1}).status_code == 404


def test_logs_admin_only(admin, president):
    assert client.get('/api/logs', headers=president).status_code == 403
    body = client.get('/api/logs', headers=admin).json()
    assert body['rows'] and {s['status'] for s in body['stats']} >= {'REJECTED_PERMISSION'}

# ---- Thành viên (BR09, che thông tin liên lạc) ----


def test_member_contact_info_masked(event_team, president):
    assert all(m['email'] is None for m in client.get('/api/members', headers=event_team).json())
    assert any(m['email'] for m in client.get('/api/members', headers=president).json())


def test_member_crud_and_br09(president, event_team, conn):
    body = {'first_name': 'Lan', 'last_name': 'Pham', 'email': 'lan@lpu.edu', 'position': 'Member',
            'zip': 55108}
    assert client.post('/api/members', headers=event_team, json=body).status_code == 403
    assert client.post('/api/members', headers=president, json=body | {'zip': 1}).status_code == 422
    mid = client.post('/api/members', headers=president, json=body).json()['id']
    assert client.put(f'/api/members/{mid}', headers=president, json=body | {'position': 'Secretary'}).status_code == 200
    assert client.delete(f'/api/members/{mid}', headers=president).status_code == 200
    used = conn.execute('SELECT link_to_member FROM attendance LIMIT 1').fetchone()[0]
    assert client.delete(f'/api/members/{used}', headers=president).status_code == 409
    actions = [r[0] for r in conn.execute("SELECT action FROM audit_log WHERE entity = 'member' AND entity_id = ?",
                                          (mid,))]
    assert actions == ['CREATE', 'UPDATE', 'DELETE']  # BR10

# ---- Sự kiện, điểm danh (BR11, BR12) ----


def test_event_lifecycle_and_attendance(event_team, treasurer):
    ev = {'event_name': 'Workshop Git', 'event_date': '2026-12-05T18:00', 'type': 'Meeting', 'location': 'MU 215'}
    assert client.post('/api/events', headers=treasurer, json=ev).status_code == 403
    assert client.post('/api/events', headers=event_team, json=ev | {'status': 'Open'}).status_code == 422
    eid = client.post('/api/events', headers=event_team, json=ev).json()['id']
    members = [m['member_id'] for m in client.get('/api/members', headers=event_team).json()[:3]]
    url = f'/api/events/{eid}/attendance'
    assert client.put(url, headers=event_team, json={'member_ids': members}).status_code == 409  # Planning
    assert client.put(f'/api/events/{eid}', headers=event_team, json=ev | {'status': 'Open'}).status_code == 200
    assert client.put(url, headers=event_team, json={'member_ids': members}).json()['count'] == 3
    assert client.get(f'/api/events/{eid}', headers=event_team).json()['attendees'] == sorted(members)
    assert client.put(f'/api/events/{eid}', headers=event_team, json=ev | {'status': 'Closed'}).status_code == 200
    assert client.put(f'/api/events/{eid}', headers=event_team, json=ev | {'status': 'Open'}).status_code == 422
    assert client.put(url, headers=event_team, json={'member_ids': []}).status_code == 409  # Closed
    assert client.delete(f'/api/events/{eid}', headers=event_team).status_code == 409  # có điểm danh

# ---- Tài chính: duyệt chi (BR06, BR07, BR08) ----


def test_finance_hidden_from_event_team(event_team):
    for path in ('/api/budgets', '/api/expenses', '/api/incomes', '/api/reports/finance'):
        assert client.get(path, headers=event_team).status_code == 403
    assert client.get('/api/dashboard', headers=event_team).json()['finance'] is None


def test_expense_approval_updates_budget(treasurer, president):
    b = open_budget(treasurer, min_remaining=10)
    x = {'expense_description': 'Bánh nước', 'expense_date': '2026-11-20', 'cost': 7.5,
         'link_to_budget': b['budget_id']}
    assert client.post('/api/expenses', headers=president, json=x).status_code == 403  # chủ nhiệm không lập chi
    eid = client.post('/api/expenses', headers=treasurer, json=x).json()['id']
    assert client.post(f'/api/expenses/{eid}/approve', headers=treasurer).status_code == 403
    assert client.get('/api/dashboard', headers=president).json()['finance']['pending_count'] >= 1
    assert client.post(f'/api/expenses/{eid}/approve', headers=president).status_code == 200
    after = next(y for y in client.get('/api/budgets', headers=treasurer).json() if y['budget_id'] == b['budget_id'])
    assert after['spent'] == round(b['spent'] + 7.5, 2) and after['remaining'] == round(b['remaining'] - 7.5, 2)
    assert client.post(f'/api/expenses/{eid}/approve', headers=president).status_code == 409  # đã xử lý
    assert client.delete(f'/api/expenses/{eid}', headers=treasurer).status_code == 409


def test_expense_over_budget_cannot_be_approved(treasurer, president):
    b = open_budget(treasurer)
    x = {'expense_description': 'Thuê âm thanh', 'expense_date': '2026-11-21', 'cost': b['remaining'] + 100,
         'link_to_budget': b['budget_id']}
    r = client.post('/api/expenses', headers=treasurer, json=x).json()
    assert r['warning']
    assert client.post(f'/api/expenses/{r["id"]}/approve', headers=president).status_code == 409  # BR07
    assert client.post(f'/api/expenses/{r["id"]}/reject', headers=president, json={}).status_code == 422
    assert client.post(f'/api/expenses/{r["id"]}/reject', headers=president,
                       json={'note': 'Vượt ngân sách'}).status_code == 200
    x2 = next(e for e in client.get('/api/expenses', headers=treasurer).json() if e['expense_id'] == r['id'])
    assert x2['status'] == 'REJECTED' and x2['review_note'] == 'Vượt ngân sách'


def test_proposer_cannot_approve_own_expense(admin, treasurer):
    client.post('/api/users', headers=admin, json={'username': 'kiemnhiem', 'full_name': 'Kiêm nhiệm',
                                                   'role': 'treasurer', 'password': 'kiem123'})
    h = login('kiemnhiem', 'kiem123')
    b = open_budget(treasurer, min_remaining=1)
    eid = client.post('/api/expenses', headers=h, json={'expense_description': 'Giấy in', 'expense_date': '2026-11-22',
                                                        'cost': 1, 'link_to_budget': b['budget_id']}).json()['id']
    body = {'expense_description': 'Giấy in A4', 'expense_date': '2026-11-22', 'cost': 1, 'link_to_budget': b['budget_id']}
    assert client.put(f'/api/expenses/{eid}', headers=treasurer, json=body).status_code == 403  # không phải người đề xuất
    assert client.delete(f'/api/expenses/{eid}', headers=treasurer).status_code == 403
    me = client.get('/api/me', headers=h).json()
    client.put(f"/api/users/{me['id']}", headers=admin,
               json={'username': 'kiemnhiem', 'full_name': 'Kiêm nhiệm', 'role': 'president'})
    assert client.post(f'/api/expenses/{eid}/approve', headers=h).status_code == 409  # BR08


def test_budget_rules(treasurer):
    b = next(x for x in client.get('/api/budgets', headers=treasurer).json() if x['spent'] > 0)
    body = {'link_to_event': b['link_to_event'], 'category': b['category'], 'amount': int(b['spent']) - 1}
    assert client.put(f"/api/budgets/{b['budget_id']}", headers=treasurer, json=body).status_code == 422
    assert client.post('/api/budgets', headers=treasurer, json=body | {'amount': 10}).status_code == 409  # trùng
    assert client.delete(f"/api/budgets/{b['budget_id']}", headers=treasurer).status_code == 409
    closed = next(e for e in client.get('/api/events', headers=treasurer).json() if e['status'] == 'Closed')
    assert client.post('/api/budgets', headers=treasurer,
                       json={'link_to_event': closed['event_id'], 'category': 'Parking', 'amount': 10}).status_code == 409


def test_income_crud(treasurer, president):
    body = {'date_received': '2026-11-01', 'amount': 50, 'source': 'Dues'}
    assert client.post('/api/incomes', headers=president, json=body).status_code == 403
    iid = client.post('/api/incomes', headers=treasurer, json=body).json()['id']
    assert client.put(f'/api/incomes/{iid}', headers=treasurer, json=body | {'amount': 60}).status_code == 200
    assert client.delete(f'/api/incomes/{iid}', headers=treasurer).status_code == 200

# ---- Từ điển, báo cáo, nhật ký thay đổi ----


def test_glossary_crud(president, event_team):
    body = {'term': 'tiệc cuối năm', 'definition': "event.type = 'Social'"}  # kiểm tra trùng không phân biệt hoa thường với chữ có dấu
    assert client.post('/api/glossary', headers=event_team, json=body).status_code == 403
    tid = client.post('/api/glossary', headers=president, json=body).json()['id']
    assert client.post('/api/glossary', headers=president, json=body | {'term': 'TIỆC CUỐI NĂM'}).status_code == 409
    assert client.put(f'/api/glossary/{tid}', headers=president, json=body | {'is_active': False}).status_code == 200
    assert client.delete(f'/api/glossary/{tid}', headers=president).status_code == 200


def test_reports(president):
    att = client.get('/api/reports/attendance', headers=president).json()
    assert att['total_events'] > 0 and len(att['members']) >= 33
    fin = client.get('/api/reports/finance', headers=president).json()
    assert fin['by_event'] and {i['source'] for i in fin['income']} >= {'Dues'}


def test_audit_permission(president, treasurer):
    assert client.get('/api/audit', headers=treasurer).status_code == 403
    assert client.get('/api/audit', headers=president).json()

# ---- UC07, UC11 ----


def test_model_config_admin_only(admin, president):
    body = {'model_tag': 'qwen2.5-coder:7b', 'base_url': 'http://localhost:11434/v1', 'is_active': True,
            'is_default': True}
    assert client.put('/api/models/1', headers=president, json=body).status_code == 403
    assert client.put('/api/models/1', headers=admin, json=body).status_code == 200
    assert client.put('/api/models/1', headers=admin, json=body | {'is_active': False}).status_code == 422


def test_user_management(admin, president):
    assert client.get('/api/users', headers=president).status_code == 403
    r = client.post('/api/users', headers=admin,
                    json={'username': 'thuquy2', 'full_name': 'Thủ quỹ 2', 'role': 'treasurer', 'password': 'tq1234'})
    assert r.status_code == 200
    assert client.post('/api/users', headers=admin, json={'username': 'x1x', 'full_name': 'X', 'role': 'member',
                                                          'password': 'abcdef'}).status_code == 422
    me = client.get('/api/me', headers=admin).json()
    assert client.put(f"/api/users/{me['id']}", headers=admin,
                      json={'username': 'admin', 'full_name': 'x', 'role': 'event'}).status_code == 422
