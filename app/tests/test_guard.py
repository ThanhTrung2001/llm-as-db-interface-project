"""BR01–BR03: lớp an toàn truy vấn."""
import pytest

from app.backend import guard, prompt
from app.backend.guard import QueryRejected


def status_of(fn, *args, **kw):
    with pytest.raises(QueryRejected) as e:
        fn(*args, **kw)
    return e.value.status


# ---- BR01: chỉ một câu SELECT ----

@pytest.mark.parametrize('sql', [
    'SELECT COUNT(*) FROM member',
    'select first_name from member;',
    "WITH x AS (SELECT REPLACE(first_name, 'a', 'b') AS n FROM member) SELECT n FROM x",
    "SELECT 'a;b' FROM member",
])
def test_select_allowed(sql):
    assert guard.check_select(sql).upper().lstrip().startswith(('SELECT', 'WITH'))


@pytest.mark.parametrize('sql', [
    'DELETE FROM member',
    'DROP TABLE member',
    'UPDATE member SET email = NULL',
    "ATTACH DATABASE 'x.db' AS x",
    'PRAGMA table_info(member)',
    'SELECT 1; DROP TABLE member',
])
def test_unsafe_rejected(sql):
    assert status_of(guard.check_select, sql) == 'REJECTED_UNSAFE'


@pytest.mark.parametrize('sql', ['', '   ', 'To find the answer we need to join tables', '-- only a comment'])
def test_not_sql_is_failed_generation(sql):
    assert status_of(guard.check_select, sql) == 'FAILED_GENERATION'


def test_write_hidden_in_cte_blocked_by_engine():
    sql = 'WITH x AS (SELECT 1) DELETE FROM member'
    assert status_of(guard.execute, guard.check_select(sql), 'admin') == 'REJECTED_UNSAFE'


# ---- BR03: phân quyền theo vai trò, chặn ở tầng engine ----

@pytest.mark.parametrize('sql', [
    'SELECT COUNT(*) FROM expense',
    'SELECT SUM(amount) FROM income',
    'SELECT 1 FROM budget LIMIT 1',
    'SELECT email FROM member',
    'SELECT * FROM member',
    'SELECT m.first_name FROM member m JOIN expense e ON e.link_to_member = m.member_id',
    "SELECT first_name FROM member WHERE phone LIKE '%1%'",
])
def test_event_team_cannot_read_restricted(sql):
    assert status_of(guard.execute, sql, 'event') == 'REJECTED_PERMISSION'


@pytest.mark.parametrize('role', ['treasurer', 'admin'])
@pytest.mark.parametrize('sql', ['SELECT email FROM member', 'SELECT * FROM member'])
def test_only_president_reads_contact_info(role, sql):
    assert status_of(guard.execute, sql, role) == 'REJECTED_PERMISSION'
    guard.execute(sql, 'president')


def test_event_team_can_read_allowed_data():
    cols, rows = guard.execute("SELECT COUNT(*) FROM event WHERE type = 'Meeting'", 'event')
    assert rows[0][0] > 0


@pytest.mark.parametrize('role', ['president', 'treasurer', 'admin'])
def test_finance_roles_can_read_finance(role):
    _, rows = guard.execute('SELECT SUM(cost) FROM expense', role)
    assert rows[0][0] > 0


def test_unknown_role_gets_most_restricted():
    assert status_of(guard.execute, 'SELECT SUM(amount) FROM income', 'nobody') == 'REJECTED_PERMISSION'


def test_schema_prompt_follows_permission_matrix():
    s = prompt.schema_prompt('event')
    assert 'expense' not in s and 'income' not in s and '"budget"' not in s
    assert 'email' not in s and 'phone' not in s
    assert 'first_name' in s and 'attendance' in s
    t = prompt.schema_prompt('treasurer')
    assert 'expense' in t and 'email' not in t
    full = prompt.schema_prompt('president')
    assert 'expense' in full and 'email' in full


# ---- BR02: timeout, CSDL nguồn chỉ đọc ----

def test_timeout():
    slow = ('WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) '
            'SELECT COUNT(*) FROM c')
    assert status_of(guard.execute, slow, 'admin', timeout_s=0.5) == 'TIMEOUT'


def test_club_db_opened_read_only_for_questions():
    conn = guard.connect_readonly()
    try:
        with pytest.raises(Exception, match='readonly'):
            conn.execute("UPDATE member SET first_name = 'x'")
    finally:
        conn.close()


def test_exec_error():
    assert status_of(guard.execute, 'SELECT no_such_col FROM member', 'admin') == 'EXEC_ERROR'
