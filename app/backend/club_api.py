"""
Nghiệp vụ quản lý CLB trên club.sqlite: thành viên, sự kiện, điểm danh, ngân sách, khoản chi (có duyệt),
khoản thu, tổng quan, báo cáo, từ điển thuật ngữ, nhật ký thay đổi.
Mọi thao tác ghi đều ghi audit_log trong cùng giao dịch (BR10).
"""
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import config
from .appdb import audit, new_id, now
from .deps import current_user, db, need, one, rows

router = APIRouter(prefix='/api')

POSITIONS = ['President', 'Vice President', 'Secretary', 'Treasurer', 'Member', 'Inactive']
SHIRT_SIZES = ['Small', 'Medium', 'Large', 'X-Large']
EVENT_TYPES = ['Meeting', 'Election', 'Game', 'Guest Speaker', 'Social', 'Community Service', 'Budget',
               'Registration']
EVENT_STATUSES = ['Planning', 'Open', 'Closed']
# BR11: vòng đời sự kiện chỉ đi một chiều
EVENT_TRANSITIONS = {'Planning': {'Planning', 'Open', 'Closed'}, 'Open': {'Open', 'Closed'}, 'Closed': {'Closed'}}
BUDGET_CATEGORIES = ['Advertisement', 'Food', 'Parking', 'Speaker Gifts', 'Club T-Shirts']
INCOME_SOURCES = ['Dues', 'Fundraising', 'Sponsorship', 'School Appropration']
DATE_RE = r'^\d{4}-\d{2}-\d{2}$'
DATETIME_RE = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$'
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

# approved trong dữ liệu gốc là 'true' (31 khoản) hoặc NULL (1 khoản cũ, coi như đã duyệt)
EXPENSE_STATUS_SQL = ("CASE COALESCE(e.approved, 'true') WHEN 'true' THEN 'APPROVED' "
                      "WHEN 'pending' THEN 'PENDING' ELSE 'REJECTED' END")
MEMBER_NAME = "(m.first_name || ' ' || m.last_name)"


def _404(what: str):
    raise HTTPException(404, f'{what} not found')


def _clean(d: dict) -> dict:
    return {k: (v.strip() or None) if isinstance(v, str) else v for k, v in d.items()}

# ---------- Danh mục dùng cho form ----------


@router.get('/lookups')
def lookups(user=Depends(current_user), conn=Depends(db)):
    return {
        'positions': POSITIONS, 'shirt_sizes': SHIRT_SIZES, 'event_types': EVENT_TYPES,
        'event_statuses': EVENT_STATUSES, 'budget_categories': BUDGET_CATEGORIES, 'income_sources': INCOME_SOURCES,
        'majors': rows(conn, 'SELECT major_id AS id, major_name AS name, department FROM major ORDER BY major_name'),
        'members': rows(conn, f"SELECT member_id AS id, {MEMBER_NAME} AS name, position FROM member m "
                              "ORDER BY first_name, last_name"),
        'events': rows(conn, 'SELECT event_id AS id, event_name AS name, event_date AS date, status '
                             'FROM event ORDER BY event_date DESC'),
    }

# ---------- Thành viên ----------


class MemberIn(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    email: Optional[str] = None
    phone: Optional[str] = None
    position: str = 'Member'
    t_shirt_size: Optional[str] = None
    zip: Optional[int] = None
    link_to_major: Optional[str] = None


def _validate_member(conn, body: MemberIn) -> dict:
    d = _clean(body.model_dump())
    if d['position'] not in POSITIONS:
        raise HTTPException(422, 'Invalid position')
    if d['t_shirt_size'] and d['t_shirt_size'] not in SHIRT_SIZES:
        raise HTTPException(422, 'Invalid T-shirt size')
    if d['email'] and not EMAIL_RE.match(d['email']):
        raise HTTPException(422, 'Invalid email')
    if d['zip'] is not None and not one(conn, 'SELECT 1 AS x FROM zip_code WHERE zip_code = ?', (d['zip'],)):
        raise HTTPException(422, f'ZIP code {d["zip"]} does not exist')
    if d['link_to_major'] and not one(conn, 'SELECT 1 AS x FROM major WHERE major_id = ?', (d['link_to_major'],)):
        raise HTTPException(422, 'Major does not exist')
    return d


def _mask_member(user, m: dict) -> dict:
    if not config.can(user['role'], 'pii.read'):
        m['email'] = m['phone'] = None
    return m


@router.get('/members')
def members(user=Depends(current_user), conn=Depends(db)):
    data = rows(conn, f"""
        SELECT m.*, {MEMBER_NAME} AS full_name, mj.major_name, mj.department, z.city, z.state,
               (SELECT COUNT(*) FROM attendance a WHERE a.link_to_member = m.member_id) AS attended
        FROM member m LEFT JOIN major mj ON mj.major_id = m.link_to_major
        LEFT JOIN zip_code z ON z.zip_code = m.zip
        ORDER BY m.position = 'Inactive', m.first_name, m.last_name""")
    return [_mask_member(user, m) for m in data]


@router.get('/members/{member_id}')
def member_detail(member_id: str, user=Depends(current_user), conn=Depends(db)):
    m = one(conn, f'SELECT m.*, {MEMBER_NAME} AS full_name, mj.major_name FROM member m '
                  'LEFT JOIN major mj ON mj.major_id = m.link_to_major WHERE member_id = ?', (member_id,))
    if not m:
        _404('Member')
    m['events'] = rows(conn, 'SELECT e.event_id, e.event_name, e.event_date, e.type FROM attendance a '
                             'JOIN event e ON e.event_id = a.link_to_event WHERE a.link_to_member = ? '
                             'ORDER BY e.event_date DESC', (member_id,))
    return _mask_member(user, m)


@router.post('/members')
def add_member(body: MemberIn, user=Depends(need('member.write')), conn=Depends(db)):
    d = _validate_member(conn, body)
    d['member_id'] = new_id()
    conn.execute('INSERT INTO member (member_id, first_name, last_name, email, position, t_shirt_size, phone, zip, '
                 'link_to_major) VALUES (:member_id, :first_name, :last_name, :email, :position, :t_shirt_size, '
                 ':phone, :zip, :link_to_major)', d)
    audit(conn, user, 'CREATE', 'member', d['member_id'], f'Created member {d["first_name"]} {d["last_name"]}',
          after=d)
    conn.commit()
    return {'id': d['member_id']}


@router.put('/members/{member_id}')
def update_member(member_id: str, body: MemberIn, user=Depends(need('member.write')), conn=Depends(db)):
    before = one(conn, 'SELECT * FROM member WHERE member_id = ?', (member_id,))
    if not before:
        _404('Member')
    d = _validate_member(conn, body) | {'member_id': member_id}
    conn.execute('UPDATE member SET first_name = :first_name, last_name = :last_name, email = :email, '
                 'position = :position, t_shirt_size = :t_shirt_size, phone = :phone, zip = :zip, '
                 'link_to_major = :link_to_major WHERE member_id = :member_id', d)
    audit(conn, user, 'UPDATE', 'member', member_id, f'Updated member {d["first_name"]} {d["last_name"]}',
          before, d)
    conn.commit()
    return {'ok': True}


@router.delete('/members/{member_id}')
def delete_member(member_id: str, user=Depends(need('member.write')), conn=Depends(db)):
    before = one(conn, 'SELECT * FROM member WHERE member_id = ?', (member_id,))
    if not before:
        _404('Member')
    used = conn.execute('SELECT (SELECT COUNT(*) FROM attendance WHERE link_to_member = ?) + '
                        '(SELECT COUNT(*) FROM expense WHERE link_to_member = ?) + '
                        '(SELECT COUNT(*) FROM income WHERE link_to_member = ?)',
                        (member_id,) * 3).fetchone()[0]
    if used:  # BR09
        raise HTTPException(409, 'This member has attendance or financial records and cannot be deleted. '
                                 'Change their position to "Inactive" instead.')
    conn.execute('DELETE FROM member WHERE member_id = ?', (member_id,))
    audit(conn, user, 'DELETE', 'member', member_id,
          f'Deleted member {before["first_name"]} {before["last_name"]}', before)
    conn.commit()
    return {'ok': True}

# ---------- Sự kiện và điểm danh ----------


class EventIn(BaseModel):
    event_name: str = Field(..., min_length=2, max_length=120)
    event_date: str = Field(..., pattern=DATETIME_RE)
    type: str
    location: Optional[str] = None
    notes: Optional[str] = None
    status: str = 'Planning'


@router.get('/events')
def events(user=Depends(current_user), conn=Depends(db)):
    fin = config.can(user['role'], 'finance.read')
    budget_col = (', (SELECT SUM(amount) FROM budget b WHERE b.link_to_event = e.event_id) AS budget_amount, '
                  '(SELECT SUM(spent) FROM budget b WHERE b.link_to_event = e.event_id) AS budget_spent') if fin else ''
    return rows(conn, f"""SELECT e.*, (SELECT COUNT(*) FROM attendance a WHERE a.link_to_event = e.event_id)
                          AS attendees {budget_col} FROM event e ORDER BY e.event_date DESC""")


@router.get('/events/{event_id}')
def event_detail(event_id: str, user=Depends(current_user), conn=Depends(db)):
    e = one(conn, 'SELECT * FROM event WHERE event_id = ?', (event_id,))
    if not e:
        _404('Event')
    e['attendees'] = [r['link_to_member'] for r in
                      rows(conn, 'SELECT link_to_member FROM attendance WHERE link_to_event = ?', (event_id,))]
    if config.can(user['role'], 'finance.read'):
        e['budgets'] = rows(conn, 'SELECT * FROM budget WHERE link_to_event = ? ORDER BY category', (event_id,))
    return e


def _validate_event(body: EventIn) -> dict:
    d = _clean(body.model_dump())
    if d['type'] not in EVENT_TYPES:
        raise HTTPException(422, 'Invalid event type')
    if d['status'] not in EVENT_STATUSES:
        raise HTTPException(422, 'Invalid status')
    if len(d['event_date']) == 16:
        d['event_date'] += ':00'
    return d


@router.post('/events')
def add_event(body: EventIn, user=Depends(need('event.write')), conn=Depends(db)):
    d = _validate_event(body)
    if d['status'] != 'Planning':
        raise HTTPException(422, 'A new event must have status "Planning"')
    d['event_id'] = new_id()
    conn.execute('INSERT INTO event (event_id, event_name, event_date, type, notes, location, status) '
                 'VALUES (:event_id, :event_name, :event_date, :type, :notes, :location, :status)', d)
    audit(conn, user, 'CREATE', 'event', d['event_id'], f'Created event "{d["event_name"]}"', after=d)
    conn.commit()
    return {'id': d['event_id']}


@router.put('/events/{event_id}')
def update_event(event_id: str, body: EventIn, user=Depends(need('event.write')), conn=Depends(db)):
    before = one(conn, 'SELECT * FROM event WHERE event_id = ?', (event_id,))
    if not before:
        _404('Event')
    d = _validate_event(body) | {'event_id': event_id}
    if d['status'] not in EVENT_TRANSITIONS.get(before['status'], set(EVENT_STATUSES)):  # BR11
        raise HTTPException(422, f'Cannot change event status from "{before["status"]}" back to "{d["status"]}"')
    conn.execute('UPDATE event SET event_name = :event_name, event_date = :event_date, type = :type, '
                 'notes = :notes, location = :location, status = :status WHERE event_id = :event_id', d)
    # budget.event_status là bản sao trạng thái sự kiện trong dữ liệu gốc → giữ đồng bộ
    conn.execute('UPDATE budget SET event_status = ? WHERE link_to_event = ?', (d['status'], event_id))
    action = f'status {before["status"]} → {d["status"]}' if before['status'] != d['status'] else 'edited'
    audit(conn, user, 'UPDATE', 'event', event_id, f'Event "{d["event_name"]}": {action}', before, d)
    conn.commit()
    return {'ok': True}


@router.delete('/events/{event_id}')
def delete_event(event_id: str, user=Depends(need('event.write')), conn=Depends(db)):
    before = one(conn, 'SELECT * FROM event WHERE event_id = ?', (event_id,))
    if not before:
        _404('Event')
    used = conn.execute('SELECT (SELECT COUNT(*) FROM attendance WHERE link_to_event = ?) + '
                        '(SELECT COUNT(*) FROM budget WHERE link_to_event = ?)', (event_id, event_id)).fetchone()[0]
    if used:
        raise HTTPException(409, 'This event has attendance or budgets and cannot be deleted. '
                                 'Change its status to "Closed" instead.')
    conn.execute('DELETE FROM event WHERE event_id = ?', (event_id,))
    audit(conn, user, 'DELETE', 'event', event_id, f'Deleted event "{before["event_name"]}"', before)
    conn.commit()
    return {'ok': True}


class AttendanceIn(BaseModel):
    member_ids: List[str]


@router.put('/events/{event_id}/attendance')
def set_attendance(event_id: str, body: AttendanceIn, user=Depends(need('attendance.write')), conn=Depends(db)):
    e = one(conn, 'SELECT * FROM event WHERE event_id = ?', (event_id,))
    if not e:
        _404('Event')
    if e['status'] != 'Open':  # BR12
        raise HTTPException(409, 'Attendance can only be recorded while the event is Open.')
    ids = sorted(set(body.member_ids))
    known = {r['member_id'] for r in rows(conn, 'SELECT member_id FROM member')}
    if set(ids) - known:
        raise HTTPException(422, 'The list contains a member that does not exist')
    before = sorted(r['link_to_member'] for r in
                    rows(conn, 'SELECT link_to_member FROM attendance WHERE link_to_event = ?', (event_id,)))
    conn.execute('DELETE FROM attendance WHERE link_to_event = ?', (event_id,))
    conn.executemany('INSERT INTO attendance (link_to_event, link_to_member) VALUES (?,?)',
                     [(event_id, m) for m in ids])
    added, removed = len(set(ids) - set(before)), len(set(before) - set(ids))
    audit(conn, user, 'UPDATE', 'attendance', event_id,
          f'Attendance for "{e["event_name"]}": {len(ids)} people (+{added}, -{removed})',
          {'members': before}, {'members': ids})
    conn.commit()
    return {'count': len(ids)}

# ---------- Ngân sách ----------


def recompute_budget(conn, budget_id: str) -> None:
    """BR06: spent = tổng các khoản chi đã duyệt; remaining = amount - spent."""
    conn.execute("""UPDATE budget SET
        spent = ROUND((SELECT COALESCE(SUM(cost), 0) FROM expense e
                 WHERE e.link_to_budget = budget.budget_id AND COALESCE(e.approved, 'true') = 'true'), 2),
        remaining = ROUND(amount - (SELECT COALESCE(SUM(cost), 0) FROM expense e
                 WHERE e.link_to_budget = budget.budget_id AND COALESCE(e.approved, 'true') = 'true'), 2)
        WHERE budget_id = ?""", (budget_id,))


class BudgetIn(BaseModel):
    link_to_event: str
    category: str
    amount: int = Field(..., gt=0, le=1_000_000)


@router.get('/budgets')
def budgets(user=Depends(need('finance.read')), conn=Depends(db)):
    return rows(conn, """SELECT b.*, e.event_name, e.event_date,
        (SELECT COUNT(*) FROM expense x WHERE x.link_to_budget = b.budget_id) AS n_expenses,
        (SELECT COALESCE(SUM(cost), 0) FROM expense x WHERE x.link_to_budget = b.budget_id
           AND x.approved = 'pending') AS pending
        FROM budget b JOIN event e ON e.event_id = b.link_to_event ORDER BY e.event_date DESC, b.category""")


@router.post('/budgets')
def add_budget(body: BudgetIn, user=Depends(need('finance.write')), conn=Depends(db)):
    e = one(conn, 'SELECT * FROM event WHERE event_id = ?', (body.link_to_event,))
    if not e:
        _404('Event')
    if e['status'] == 'Closed':
        raise HTTPException(409, 'The event is closed; no more budgets can be created')
    if body.category not in BUDGET_CATEGORIES:
        raise HTTPException(422, 'Invalid category')
    if one(conn, 'SELECT 1 AS x FROM budget WHERE link_to_event = ? AND category = ?',
           (body.link_to_event, body.category)):
        raise HTTPException(409, f'The event already has a budget for category "{body.category}"')
    bid = new_id()
    conn.execute('INSERT INTO budget (budget_id, category, spent, remaining, amount, event_status, link_to_event) '
                 'VALUES (?,?,0,?,?,?,?)', (bid, body.category, body.amount, body.amount, e['status'], e['event_id']))
    audit(conn, user, 'CREATE', 'budget', bid,
          f'Created {body.category} budget ${body.amount} for "{e["event_name"]}"', after=body.model_dump())
    conn.commit()
    return {'id': bid}


@router.put('/budgets/{budget_id}')
def update_budget(budget_id: str, body: BudgetIn, user=Depends(need('finance.write')), conn=Depends(db)):
    before = one(conn, 'SELECT * FROM budget WHERE budget_id = ?', (budget_id,))
    if not before:
        _404('Budget')
    if body.amount < (before['spent'] or 0):
        raise HTTPException(422, f'The budget cannot be less than the amount already spent (${before["spent"]})')
    conn.execute('UPDATE budget SET amount = ? WHERE budget_id = ?', (body.amount, budget_id))
    recompute_budget(conn, budget_id)
    audit(conn, user, 'UPDATE', 'budget', budget_id,
          f'Changed {before["category"]} budget: ${before["amount"]} → ${body.amount}', before, body.model_dump())
    conn.commit()
    return {'ok': True}


@router.delete('/budgets/{budget_id}')
def delete_budget(budget_id: str, user=Depends(need('finance.write')), conn=Depends(db)):
    before = one(conn, 'SELECT * FROM budget WHERE budget_id = ?', (budget_id,))
    if not before:
        _404('Budget')
    if one(conn, 'SELECT 1 AS x FROM expense WHERE link_to_budget = ?', (budget_id,)):
        raise HTTPException(409, 'This budget has expenses and cannot be deleted')
    conn.execute('DELETE FROM budget WHERE budget_id = ?', (budget_id,))
    audit(conn, user, 'DELETE', 'budget', budget_id, f'Deleted {before["category"]} budget', before)
    conn.commit()
    return {'ok': True}

# ---------- Khoản chi và quy trình duyệt ----------


class ExpenseIn(BaseModel):
    expense_description: str = Field(..., min_length=2, max_length=200)
    expense_date: str = Field(..., pattern=DATE_RE)
    cost: float = Field(..., gt=0, le=1_000_000)
    link_to_budget: str
    link_to_member: Optional[str] = None


class ReviewIn(BaseModel):
    note: Optional[str] = None


EXPENSE_SELECT = f"""SELECT e.*, {EXPENSE_STATUS_SQL} AS status, b.category, b.remaining AS budget_remaining,
    ev.event_name, {MEMBER_NAME} AS member_name,
    r.proposed_at, r.reviewed_at, r.note AS review_note, pu.full_name AS proposed_by_name,
    ru.full_name AS reviewed_by_name, r.proposed_by
    FROM expense e LEFT JOIN budget b ON b.budget_id = e.link_to_budget
    LEFT JOIN event ev ON ev.event_id = b.link_to_event
    LEFT JOIN member m ON m.member_id = e.link_to_member
    LEFT JOIN expense_review r ON r.expense_id = e.expense_id
    LEFT JOIN user_account pu ON pu.id = r.proposed_by LEFT JOIN user_account ru ON ru.id = r.reviewed_by """


@router.get('/expenses')
def expenses(user=Depends(need('finance.read')), conn=Depends(db)):
    return rows(conn, EXPENSE_SELECT + "ORDER BY e.approved = 'pending' DESC, e.expense_date DESC")


def _expense(conn, expense_id: str) -> dict:
    x = one(conn, EXPENSE_SELECT + 'WHERE e.expense_id = ?', (expense_id,))
    if not x:
        _404('Expense')
    return x


def _validate_expense(conn, body: ExpenseIn) -> dict:
    d = _clean(body.model_dump())
    b = one(conn, 'SELECT * FROM budget WHERE budget_id = ?', (d['link_to_budget'],))
    if not b:
        raise HTTPException(422, 'Budget does not exist')
    if b['event_status'] == 'Closed':
        raise HTTPException(409, 'The event is closed; no more expenses can be proposed')
    if d['link_to_member'] and not one(conn, 'SELECT 1 AS x FROM member WHERE member_id = ?',
                                       (d['link_to_member'],)):
        raise HTTPException(422, 'Member does not exist')
    d['cost'] = round(d['cost'], 2)
    return d | {'_remaining': b['remaining']}


@router.post('/expenses')
def add_expense(body: ExpenseIn, user=Depends(need('finance.write')), conn=Depends(db)):
    d = _validate_expense(conn, body)
    remaining = d.pop('_remaining')
    d['expense_id'] = new_id()
    conn.execute("INSERT INTO expense (expense_id, expense_description, expense_date, cost, approved, "
                 "link_to_member, link_to_budget) VALUES (:expense_id, :expense_description, :expense_date, :cost, "
                 "'pending', :link_to_member, :link_to_budget)", d)
    conn.execute('INSERT INTO expense_review (expense_id, proposed_by, proposed_at) VALUES (?,?,?)',
                 (d['expense_id'], user['id'], now()))
    audit(conn, user, 'CREATE', 'expense', d['expense_id'],
          f'Proposed expense "{d["expense_description"]}" ${d["cost"]}', after=d)
    conn.commit()
    warning = (f'This expense exceeds the remaining budget (${remaining}). The President cannot approve it unless '
               'the budget is increased.') if d['cost'] > (remaining or 0) else None  # BR07 (cảnh báo sớm)
    return {'id': d['expense_id'], 'warning': warning}


@router.put('/expenses/{expense_id}')
def update_expense(expense_id: str, body: ExpenseIn, user=Depends(need('finance.write')), conn=Depends(db)):
    before = _expense(conn, expense_id)
    if before['status'] != 'PENDING':
        raise HTTPException(409, 'Only pending expenses can be edited')
    if before['proposed_by'] != user['id']:
        raise HTTPException(403, 'Only the proposer can edit this expense')
    d = _validate_expense(conn, body)
    d.pop('_remaining')
    conn.execute('UPDATE expense SET expense_description = :expense_description, expense_date = :expense_date, '
                 'cost = :cost, link_to_member = :link_to_member, link_to_budget = :link_to_budget '
                 'WHERE expense_id = :expense_id', d | {'expense_id': expense_id})
    audit(conn, user, 'UPDATE', 'expense', expense_id, f'Updated expense proposal "{d["expense_description"]}"',
          before, d)
    conn.commit()
    return {'ok': True}


@router.delete('/expenses/{expense_id}')
def delete_expense(expense_id: str, user=Depends(need('finance.write')), conn=Depends(db)):
    before = _expense(conn, expense_id)
    if before['status'] != 'PENDING':
        raise HTTPException(409, 'Only pending expenses can be withdrawn')
    if before['proposed_by'] != user['id']:
        raise HTTPException(403, 'Only the proposer can withdraw this expense')
    conn.execute('DELETE FROM expense WHERE expense_id = ?', (expense_id,))
    conn.execute('DELETE FROM expense_review WHERE expense_id = ?', (expense_id,))
    audit(conn, user, 'DELETE', 'expense', expense_id, f'Withdrew expense proposal "{before["expense_description"]}"',
          before)
    conn.commit()
    return {'ok': True}


def _review(conn, user, expense_id: str, approve: bool, note: Optional[str]):
    x = _expense(conn, expense_id)
    if x['status'] != 'PENDING':
        raise HTTPException(409, 'This expense has already been reviewed')
    if x['proposed_by'] == user['id']:  # BR08
        raise HTTPException(409, 'You cannot review an expense you proposed')
    if approve and x['cost'] > (x['budget_remaining'] or 0):  # BR07
        raise HTTPException(409, f'Cannot approve: the ${x["cost"]} expense exceeds the remaining budget of '
                                 f'${x["budget_remaining"]} for category {x["category"]}')
    if not approve and not (note or '').strip():
        raise HTTPException(422, 'Please enter a reason for rejection')
    conn.execute('UPDATE expense SET approved = ? WHERE expense_id = ?', ('true' if approve else 'false', expense_id))
    conn.execute('UPDATE expense_review SET reviewed_by = ?, reviewed_at = ?, note = ? WHERE expense_id = ?',
                 (user['id'], now(), (note or '').strip() or None, expense_id))
    recompute_budget(conn, x['link_to_budget'])  # BR06
    audit(conn, user, 'APPROVE' if approve else 'REJECT', 'expense', expense_id,
          f'{"Approved" if approve else "Rejected"} expense "{x["expense_description"]}" ${x["cost"]}'
          + (f' — {note.strip()}' if note and note.strip() else ''))
    conn.commit()
    return {'ok': True}


@router.post('/expenses/{expense_id}/approve')
def approve_expense(expense_id: str, body: ReviewIn = ReviewIn(), user=Depends(need('expense.approve')),
                    conn=Depends(db)):
    return _review(conn, user, expense_id, True, body.note)


@router.post('/expenses/{expense_id}/reject')
def reject_expense(expense_id: str, body: ReviewIn, user=Depends(need('expense.approve')), conn=Depends(db)):
    return _review(conn, user, expense_id, False, body.note)

# ---------- Khoản thu ----------


class IncomeIn(BaseModel):
    date_received: str = Field(..., pattern=DATE_RE)
    amount: int = Field(..., gt=0, le=1_000_000)
    source: str
    notes: Optional[str] = None
    link_to_member: Optional[str] = None


def _validate_income(conn, body: IncomeIn) -> dict:
    d = _clean(body.model_dump())
    if d['source'] not in INCOME_SOURCES:
        raise HTTPException(422, 'Invalid income source')
    if d['link_to_member'] and not one(conn, 'SELECT 1 AS x FROM member WHERE member_id = ?',
                                       (d['link_to_member'],)):
        raise HTTPException(422, 'Member does not exist')
    return d


@router.get('/incomes')
def incomes(user=Depends(need('finance.read')), conn=Depends(db)):
    return rows(conn, f'SELECT i.*, {MEMBER_NAME} AS member_name FROM income i '
                      'LEFT JOIN member m ON m.member_id = i.link_to_member ORDER BY i.date_received DESC')


@router.post('/incomes')
def add_income(body: IncomeIn, user=Depends(need('finance.write')), conn=Depends(db)):
    d = _validate_income(conn, body) | {'income_id': new_id()}
    conn.execute('INSERT INTO income (income_id, date_received, amount, source, notes, link_to_member) '
                 'VALUES (:income_id, :date_received, :amount, :source, :notes, :link_to_member)', d)
    audit(conn, user, 'CREATE', 'income', d['income_id'], f'Recorded {d["source"]} income ${d["amount"]}', after=d)
    conn.commit()
    return {'id': d['income_id']}


@router.put('/incomes/{income_id}')
def update_income(income_id: str, body: IncomeIn, user=Depends(need('finance.write')), conn=Depends(db)):
    before = one(conn, 'SELECT * FROM income WHERE income_id = ?', (income_id,))
    if not before:
        _404('Income')
    d = _validate_income(conn, body) | {'income_id': income_id}
    conn.execute('UPDATE income SET date_received = :date_received, amount = :amount, source = :source, '
                 'notes = :notes, link_to_member = :link_to_member WHERE income_id = :income_id', d)
    audit(conn, user, 'UPDATE', 'income', income_id, f'Updated {d["source"]} income ${d["amount"]}', before, d)
    conn.commit()
    return {'ok': True}


@router.delete('/incomes/{income_id}')
def delete_income(income_id: str, user=Depends(need('finance.write')), conn=Depends(db)):
    before = one(conn, 'SELECT * FROM income WHERE income_id = ?', (income_id,))
    if not before:
        _404('Income')
    conn.execute('DELETE FROM income WHERE income_id = ?', (income_id,))
    audit(conn, user, 'DELETE', 'income', income_id, f'Deleted {before["source"]} income ${before["amount"]}', before)
    conn.commit()
    return {'ok': True}

# ---------- Tổng quan ----------


@router.get('/dashboard')
def dashboard(user=Depends(current_user), conn=Depends(db)):
    one_val = lambda sql, args=(): conn.execute(sql, args).fetchone()[0]  # noqa: E731
    out = {
        'members': {
            'active': one_val("SELECT COUNT(*) FROM member WHERE position <> 'Inactive'"),
            'inactive': one_val("SELECT COUNT(*) FROM member WHERE position = 'Inactive'"),
            'officers': one_val("SELECT COUNT(*) FROM member WHERE position NOT IN ('Member', 'Inactive')"),
        },
        'events_by_status': {r['status']: r['n'] for r in
                             rows(conn, 'SELECT status, COUNT(*) AS n FROM event GROUP BY status')},
        'events_by_type': rows(conn, 'SELECT type AS label, COUNT(*) AS value FROM event GROUP BY type '
                                     'ORDER BY value DESC'),
        'upcoming': rows(conn, """SELECT e.event_id, e.event_name, e.event_date, e.type, e.location, e.status,
                (SELECT COUNT(*) FROM attendance a WHERE a.link_to_event = e.event_id) AS attendees
                FROM event e WHERE e.status IN ('Planning', 'Open') ORDER BY e.event_date LIMIT 6"""),
        'avg_attendance': one_val("""SELECT ROUND(AVG(n), 1) FROM (SELECT COUNT(a.link_to_member) AS n FROM event e
                JOIN attendance a ON a.link_to_event = e.event_id GROUP BY e.event_id)"""),
        'top_attendees': rows(conn, f"""SELECT {MEMBER_NAME} AS label, COUNT(*) AS value FROM attendance a
                JOIN member m ON m.member_id = a.link_to_member GROUP BY m.member_id
                ORDER BY value DESC, label LIMIT 5"""),
        'finance': None,
    }
    if config.can(user['role'], 'finance.read'):
        out['finance'] = {
            'budget': one_val('SELECT COALESCE(SUM(amount), 0) FROM budget'),
            'spent': round(one_val('SELECT COALESCE(SUM(spent), 0) FROM budget'), 2),
            'remaining': round(one_val('SELECT COALESCE(SUM(remaining), 0) FROM budget'), 2),
            'income': one_val('SELECT COALESCE(SUM(amount), 0) FROM income'),
            'pending_count': one_val("SELECT COUNT(*) FROM expense WHERE approved = 'pending'"),
            'pending_sum': round(one_val("SELECT COALESCE(SUM(cost), 0) FROM expense WHERE approved = 'pending'"), 2),
            'spend_by_category': rows(conn, 'SELECT category AS label, ROUND(SUM(spent), 2) AS value FROM budget '
                                            'GROUP BY category ORDER BY value DESC'),
            'income_by_source': rows(conn, 'SELECT source AS label, SUM(amount) AS value FROM income '
                                           'GROUP BY source ORDER BY value DESC'),
            'monthly': rows(conn, """
                SELECT month, SUM(income) AS income, ROUND(SUM(expense), 2) AS expense FROM (
                  SELECT substr(date_received, 1, 7) AS month, amount AS income, 0 AS expense FROM income
                  UNION ALL
                  SELECT substr(expense_date, 1, 7), 0, cost FROM expense WHERE COALESCE(approved, 'true') = 'true'
                ) GROUP BY month ORDER BY month"""),
        }
    return out

# ---------- Báo cáo ----------


@router.get('/reports/attendance')
def report_attendance(user=Depends(current_user), conn=Depends(db)):
    total = conn.execute("SELECT COUNT(*) FROM event WHERE status <> 'Planning'").fetchone()[0]
    members_ = rows(conn, f"""SELECT m.member_id, {MEMBER_NAME} AS full_name, m.position, mj.major_name,
            COUNT(a.link_to_event) AS attended
            FROM member m LEFT JOIN major mj ON mj.major_id = m.link_to_major
            LEFT JOIN attendance a ON a.link_to_member = m.member_id
            GROUP BY m.member_id ORDER BY attended DESC, full_name""")
    for m in members_:
        m['rate'] = round(100 * m['attended'] / total, 1) if total else 0
    events_ = rows(conn, """SELECT e.event_id, e.event_name, e.event_date, e.type, e.status,
            COUNT(a.link_to_member) AS attendees FROM event e
            LEFT JOIN attendance a ON a.link_to_event = e.event_id
            GROUP BY e.event_id ORDER BY e.event_date""")
    return {'total_events': total, 'members': members_, 'events': events_}


@router.get('/reports/finance')
def report_finance(user=Depends(need('finance.read')), conn=Depends(db)):
    by_event = rows(conn, """SELECT e.event_id, e.event_name, e.event_date, e.status,
            SUM(b.amount) AS budget, ROUND(SUM(b.spent), 2) AS spent, ROUND(SUM(b.remaining), 2) AS remaining,
            (SELECT COUNT(*) FROM expense x JOIN budget bb ON bb.budget_id = x.link_to_budget
               WHERE bb.link_to_event = e.event_id AND COALESCE(x.approved, 'true') = 'true') AS n_expenses,
            (SELECT COALESCE(SUM(x.cost), 0) FROM expense x JOIN budget bb ON bb.budget_id = x.link_to_budget
               WHERE bb.link_to_event = e.event_id AND x.approved = 'pending') AS pending
            FROM event e JOIN budget b ON b.link_to_event = e.event_id
            GROUP BY e.event_id ORDER BY e.event_date""")
    income = rows(conn, 'SELECT source, COUNT(*) AS n, SUM(amount) AS total FROM income GROUP BY source '
                        'ORDER BY total DESC')
    return {'by_event': by_event, 'income': income}

# ---------- Từ điển thuật ngữ (UC06) ----------


class TermIn(BaseModel):
    term: str = Field(..., min_length=2, max_length=80)
    definition: str = Field(..., min_length=2, max_length=500)
    is_active: bool = True


@router.get('/glossary')
def glossary(user=Depends(current_user), conn=Depends(db)):
    return rows(conn, 'SELECT g.*, u.full_name AS updated_by_name FROM glossary_term g '
                      'LEFT JOIN user_account u ON u.id = g.updated_by ORDER BY g.term')


def _term_taken(conn, term: str, exclude_id: int = 0) -> bool:
    # COLLATE NOCASE của SQLite chỉ không phân biệt hoa thường với chữ ASCII → so bằng casefold() cho tiếng Việt
    key = term.strip().casefold()
    return any(r['term'].casefold() == key for r in
               rows(conn, 'SELECT term FROM glossary_term WHERE id <> ?', (exclude_id,)))


@router.post('/glossary')
def add_term(body: TermIn, user=Depends(need('glossary.write')), conn=Depends(db)):
    if _term_taken(conn, body.term):
        raise HTTPException(409, 'This term already exists')
    tid = conn.execute('INSERT INTO glossary_term (term, definition, is_active, updated_by, updated_at) '
                       'VALUES (?,?,?,?,?)', (body.term.strip(), body.definition.strip(), int(body.is_active),
                                              user['id'], now())).lastrowid
    audit(conn, user, 'CREATE', 'glossary', str(tid), f'Added term "{body.term.strip()}"', after=body.model_dump())
    conn.commit()
    return {'id': tid}


@router.put('/glossary/{term_id}')
def update_term(term_id: int, body: TermIn, user=Depends(need('glossary.write')), conn=Depends(db)):
    before = one(conn, 'SELECT * FROM glossary_term WHERE id = ?', (term_id,))
    if not before:
        _404('Glossary term')
    if _term_taken(conn, body.term, term_id):
        raise HTTPException(409, 'This term already exists')
    conn.execute('UPDATE glossary_term SET term = ?, definition = ?, is_active = ?, updated_by = ?, updated_at = ? '
                 'WHERE id = ?', (body.term.strip(), body.definition.strip(), int(body.is_active), user['id'],
                                  now(), term_id))
    audit(conn, user, 'UPDATE', 'glossary', str(term_id), f'Updated term "{body.term.strip()}"',
          before, body.model_dump())
    conn.commit()
    return {'ok': True}


@router.delete('/glossary/{term_id}')
def delete_term(term_id: int, user=Depends(need('glossary.write')), conn=Depends(db)):
    before = one(conn, 'SELECT * FROM glossary_term WHERE id = ?', (term_id,))
    if not before:
        _404('Glossary term')
    conn.execute('DELETE FROM glossary_term WHERE id = ?', (term_id,))
    audit(conn, user, 'DELETE', 'glossary', str(term_id), f'Deleted term "{before["term"]}"', before)
    conn.commit()
    return {'ok': True}

# ---------- Nhật ký thay đổi (BR10) ----------


@router.get('/audit')
def audit_log(entity: Optional[str] = None, user=Depends(need('audit.read')), conn=Depends(db)):
    where, args = ('WHERE a.entity = ? ', (entity,)) if entity else ('', ())
    return rows(conn, 'SELECT a.id, a.action, a.entity, a.entity_id, a.summary, a.detail, a.created_at, '
                      'u.username, u.full_name FROM audit_log a JOIN user_account u ON u.id = a.user_id '
                      + where + 'ORDER BY a.id DESC LIMIT 500', args)
