"""Cấu hình chung của ClubQuery."""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
BIRD = os.path.join(ROOT, 'src', 'DAMO-ConvAI', 'bird')
BIRD_SRC = os.path.join(BIRD, 'llm', 'src')
if BIRD_SRC not in sys.path:
    sys.path.insert(0, BIRD_SRC)  # dùng lại extract_sql, normalize_pseudo_sql của đồ án

SOURCE_DB = os.path.join(BIRD, 'data', 'dev_databases', 'student_club', 'student_club.sqlite')
APP_DB = os.environ.get('CLUBQUERY_APP_DB', os.path.join(ROOT, 'app', 'data', 'app.sqlite'))
BENCHMARK_JSON = os.path.join(ROOT, 'app', 'data', 'benchmark_student_club.json')
FRONTEND_DIR = os.path.join(ROOT, 'app', 'frontend')

QUERY_TIMEOUT_S = 10   # BR02
MAX_ROWS = 1000        # BR02

# member = Thành viên, board = Ban chủ nhiệm / Thủ quỹ, admin = Quản trị viên
ROLES = ('member', 'board', 'admin')

# BR03: dữ liệu vai trò không được đọc
RESTRICTED = {
    'member': {
        'tables': {'budget', 'expense', 'income'},
        'columns': {('member', 'email'), ('member', 'phone')},
    },
}


def restrictions(role: str) -> dict:
    return RESTRICTED.get(role, {'tables': set(), 'columns': set()})
