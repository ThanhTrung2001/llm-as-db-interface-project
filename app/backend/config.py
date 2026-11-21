"""Cấu hình chung của ClubQuery."""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
BIRD = os.path.join(ROOT, 'src', 'DAMO-ConvAI', 'bird')
BIRD_SRC = os.path.join(BIRD, 'llm', 'src')
if BIRD_SRC not in sys.path:
    sys.path.insert(0, BIRD_SRC)  # dùng lại extract_sql của các script benchmark

SOURCE_DB = os.path.join(BIRD, 'data', 'dev_databases', 'student_club', 'student_club.sqlite')
APP_DB = os.environ.get('CLUBQUERY_APP_DB', os.path.join(ROOT, 'app', 'data', 'app.sqlite'))
BENCHMARK_JSON = os.path.join(ROOT, 'app', 'data', 'benchmark_student_club.json')
FRONTEND_DIR = os.path.join(ROOT, 'app', 'frontend')

QUERY_TIMEOUT_S = 10   # chạy SQL của model quá số giây này thì ngắt
MAX_ROWS = 1000        # số dòng kết quả tối đa gửi lên giao diện
