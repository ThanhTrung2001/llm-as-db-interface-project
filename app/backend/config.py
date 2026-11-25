"""Cấu hình chung của ClubQuery: đường dẫn, giới hạn truy vấn, vai trò và ma trận quyền."""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
BIRD = os.path.join(ROOT, 'src', 'DAMO-ConvAI', 'bird')
BIRD_SRC = os.path.join(BIRD, 'llm', 'src')
if BIRD_SRC not in sys.path:
    sys.path.insert(0, BIRD_SRC)  # dùng lại extract_sql, normalize_pseudo_sql của phần nghiên cứu

# CSDL gốc của BIRD — chỉ dùng làm dữ liệu mồi, không bao giờ bị sửa
SOURCE_DB = os.path.join(BIRD, 'data', 'dev_databases', 'student_club', 'student_club.sqlite')
# Câu hỏi dev của BIRD (kèm evidence) — dùng làm danh sách câu hỏi mẫu
DEV_JSON = os.path.join(BIRD, 'data', 'dev.json')
# Bản làm việc của CLB (chép từ SOURCE_DB lần đầu chạy) — nghiệp vụ quản lý ghi vào đây
CLUB_DB = os.environ.get('CLUBQUERY_CLUB_DB', os.path.join(ROOT, 'app', 'data', 'club.sqlite'))
# Dữ liệu của ứng dụng: tài khoản, nhật ký, từ điển, quy trình duyệt chi, nhật ký thay đổi
APP_DB = os.environ.get('CLUBQUERY_APP_DB', os.path.join(ROOT, 'app', 'data', 'app.sqlite'))
FRONTEND_DIR = os.path.join(ROOT, 'app', 'frontend')

QUERY_TIMEOUT_S = 10   # BR02
MAX_ROWS = 1000        # BR02

# ---------- Vai trò và ma trận quyền (BR03, BR05) ----------
# Một ma trận dùng chung cho cả chức năng quản lý (API) lẫn hỏi đáp bằng ngôn ngữ tự nhiên (authorizer).
ROLE_NAME = {
    'president': 'President',
    'treasurer': 'Treasurer',
    'event': 'Event team',
    'admin': 'System admin',
}
ROLES = tuple(ROLE_NAME)

PERMISSIONS = {
    'president': {'member.write', 'pii.read', 'event.write', 'attendance.write', 'finance.read',
                  'expense.approve', 'glossary.write', 'audit.read'},
    'treasurer': {'finance.read', 'finance.write'},
    'event': {'event.write', 'attendance.write'},
    'admin': {'finance.read', 'glossary.write', 'audit.read', 'system.admin'},
}
PERMISSION_NAME = {
    'member.write': 'Add, edit and deactivate members',
    'pii.read': 'View member email and phone',
    'event.write': 'Add, edit and change event status',
    'attendance.write': 'Record attendance',
    'finance.read': 'View budgets, expenses and income',
    'finance.write': 'Create budgets, propose expenses, record income',
    'expense.approve': 'Approve or reject expenses',
    'glossary.write': 'Manage the glossary',
    'audit.read': 'View the change log',
    'system.admin': 'Manage accounts, models and the query log',
}

FINANCE_TABLES = {'budget', 'expense', 'income'}
PII_COLUMNS = {('member', 'email'), ('member', 'phone')}


def can(role: str, perm: str) -> bool:
    return perm in PERMISSIONS.get(role, set())


def restrictions(role: str) -> dict:
    """Bảng/cột vai trò không được đọc khi hỏi đáp (suy ra từ ma trận quyền)."""
    return {
        'tables': set() if can(role, 'finance.read') else set(FINANCE_TABLES),
        'columns': set() if can(role, 'pii.read') else set(PII_COLUMNS),
    }
