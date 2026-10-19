"""
Nghiệm thu NFR1: chấm lại 158 câu student_club × mọi lượt benchmark qua luồng của hệ thống
(chế độ phát lại, vai trò admin). Kết quả đúng/sai phải trùng với bộ chấm gốc evaluation.py
(đã lưu trong benchmark_item bởi app/scripts/per_db_ex.py).
"""
from app.backend import service


def test_replay_matches_bird_evaluator(conn):
    admin = dict(conn.execute("SELECT * FROM user_account WHERE username = 'admin'").fetchone())
    items = conn.execute('SELECT run_id, question_id, is_correct FROM benchmark_item').fetchall()
    assert len(items) == 12 * 158
    mismatches = []
    for it in items:
        r = service.ask(conn, admin, '', 'replay', run_id=it['run_id'], dev_question_id=it['question_id'])
        if (r['is_correct'] or 0) != it['is_correct']:
            mismatches.append((it['run_id'], it['question_id'], r['status'], r['error']))
    assert not mismatches, mismatches[:10]
