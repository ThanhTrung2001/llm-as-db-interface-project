"""
Demo log từng bước của LUỒNG TEXT-TO-SQL CỦA ỨNG DỤNG (ClubQuery, chế độ "Hỏi trực tiếp"), cho MỘT câu hỏi.

Gọi service.ask() y như khi bấm nút "Hỏi" trên web (POST /api/ask): đọc câu dev → chọn evidence →
dựng prompt theo vai trò → gọi LLM → tách SQL → kiểm tra an toàn → chạy chỉ đọc → diễn giải câu trả lời
→ so với đáp án → ghi nhật ký. Mỗi bước được trace.step() ghi input, tham số, hàm làm gì, output thật.

Dùng CSDL ứng dụng tạm (không ghi vào app/data/app.sqlite thật).
Cần `ollama serve` đang chạy và đã có model (mặc định Qwen2.5-Coder: qwen2.5-coder:7b).

Chạy (từ thư mục gốc repo):
  venv/Scripts/python app/scripts/trace_demo_ask.py                 # câu 1379, có evidence
  venv/Scripts/python app/scripts/trace_demo_ask.py --no_evidence   # không có evidence
  venv/Scripts/python app/scripts/trace_demo_ask.py --question_id 1400 --user thanhvien

Log ghi vào app/logs/demo_ask_<question_id>_<evidence|no_evidence>.log
"""
import argparse
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--question_id', type=int, default=1379, help='câu mẫu BIRD dev của student_club (1312–1469)')
    p.add_argument('--model', default='Qwen2.5-Coder', help='tên model trong bảng model_config (mặc định như web demo)')
    p.add_argument('--user', default='thuquy', help='admin | thuquy (board) | thanhvien (member)')
    p.add_argument('--no_evidence', action='store_true', help='bỏ tick "Dùng evidence của câu mẫu"')
    args = p.parse_args()

    config_name = 'no_evidence' if args.no_evidence else 'evidence'
    log_file = os.path.join(ROOT, 'app', 'logs', f'demo_ask_{args.question_id}_{config_name}.log')
    if os.path.exists(log_file):
        os.remove(log_file)
    os.environ['CLUBQUERY_TRACE_FILE'] = log_file
    os.environ['CLUBQUERY_TRACE'] = '1'
    os.environ['CLUBQUERY_APP_DB'] = os.path.join(tempfile.mkdtemp(prefix='clubquery_demo_'), 'app.sqlite')

    from app.backend import appdb, service, trace
    appdb.init_db(reset=True)
    conn = appdb.connect()
    try:
        user = dict(conn.execute('SELECT id, username, full_name, role FROM user_account WHERE username = ?',
                                 (args.user,)).fetchone())
        model_id = conn.execute('SELECT id FROM model_config WHERE name = ?', (args.model,)).fetchone()['id']
        trace.log.info('\n' + '#' * 100 + f'\nDEMO TEXT-TO-SQL (ứng dụng ClubQuery) — câu {args.question_id} — '
                       f'model {args.model} — {config_name}\n' + '#' * 100)
        # đúng body mà app.js gửi: {mode:'live', dev_question_id, model_id, question:'', use_evidence}
        service.ask(conn, user, '', 'live', model_id=model_id, dev_question_id=args.question_id,
                    use_evidence=not args.no_evidence)
    finally:
        conn.close()
    print(f'-> {log_file}')


if __name__ == '__main__':
    main()
