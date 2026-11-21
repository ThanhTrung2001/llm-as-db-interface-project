"""
Log từng bước cho các script app/scripts/trace_benchmark_*.py (luồng BENCHMARK, không dùng trong app web).

Mỗi bước ghi:
  - Hàm nào được gọi, hàm đó làm gì
  - Input / tham số: giá trị thật + giải thích ý nghĩa
  - Output: giá trị thật hàm trả về

Log in ra console và ghi vào file do script đặt qua CLUBQUERY_TRACE_FILE.
Biến môi trường:
  CLUBQUERY_TRACE=0          tắt log
  CLUBQUERY_TRACE_MAXLEN=N   cắt chuỗi dài hơn N ký tự (mặc định 0 = in đầy đủ, kể cả prompt)
  CLUBQUERY_TRACE_ROWS=N     số dòng kết quả SQL tối đa được in (mặc định 20)
"""
import io
import json
import logging
import os
import sys

from . import config

ENABLED = os.environ.get('CLUBQUERY_TRACE', '1') != '0'
MAXLEN = int(os.environ.get('CLUBQUERY_TRACE_MAXLEN', '0'))
MAX_ROWS = int(os.environ.get('CLUBQUERY_TRACE_ROWS', '20'))
LOG_FILE = os.environ.get('CLUBQUERY_TRACE_FILE', os.path.join(config.ROOT, 'app', 'logs', 'benchmark_trace.log'))
PREFIX = 'BENCH'  # script đặt lại: 'BENCH' (GPT-3.5) hoặc 'OLLAMA'

log = logging.getLogger('clubquery.trace')
if not log.handlers:
    log.setLevel(logging.INFO)
    log.propagate = False
    fmt = logging.Formatter('%(asctime)s %(message)s', '%H:%M:%S')
    try:  # console Windows mặc định cp1252 → in UTF-8 để không vỡ dấu tiếng Việt
        stream = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    except (AttributeError, ValueError):
        stream = sys.stderr
    sh = logging.StreamHandler(stream)
    sh.setFormatter(fmt)
    log.addHandler(sh)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        fh = logging.FileHandler(LOG_FILE, encoding='utf-8')
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except OSError:
        pass

_current = {'id': 0}  # script đặt = question_id đang trace


def _short(s: str) -> str:
    if MAXLEN and len(s) > MAXLEN:
        return s[:MAXLEN] + f'... (cắt, tổng {len(s)} ký tự)'
    return s


def fmt_value(v) -> str:
    """Biểu diễn giá trị thật, dễ đọc: chuỗi nhiều dòng giữ nguyên, bảng kết quả giới hạn số dòng."""
    if v is None:
        return 'None'
    if isinstance(v, str):
        s = _short(v)
        return repr(s) if '\n' not in s else f'(chuỗi {len(v)} ký tự)\n' + s
    if isinstance(v, (list, tuple)) and v and isinstance(v[0], (list, tuple)):
        lines = [repr(tuple(r)) for r in v[:MAX_ROWS]]
        more = f'\n... và {len(v) - MAX_ROWS} dòng nữa' if len(v) > MAX_ROWS else ''
        return f'({len(v)} dòng)\n' + '\n'.join(lines) + more
    if isinstance(v, (dict, list, tuple, set)):
        try:
            return _short(json.dumps(v if not isinstance(v, set) else sorted(v),
                                     ensure_ascii=False, default=str, indent=2))
        except TypeError:
            pass
    return _short(repr(v))


def _indent(text: str, pad: str) -> str:
    return '\n'.join(pad + line for line in text.splitlines()) if text else pad


def step(label: str, func: str, purpose: str, params=None, output=None, note: str = None,
         output_desc: str = None):
    """
    label   : số thứ tự bước, ví dụ '2b.4'
    func    : tên hàm, ví dụ 'prompt.build_prompt'
    purpose : hàm làm gì
    params  : list các (tên tham số, giá trị thật, giải thích)
    output  : giá trị thật hàm trả về
    output_desc : giải thích ý nghĩa output
    note    : ghi chú thêm (rẽ nhánh, lý do bỏ qua...)
    """
    if not ENABLED:
        return
    lines = [f'\n----- [{PREFIX} #{_current["id"]}] Bước {label}: {func} ' + '-' * max(0, 60 - len(func)),
             f'  Làm gì : {purpose}']
    if params:
        lines.append('  Input  :')
        for name, value, desc in params:
            lines.append(f'    • {name} = ' + _indent(fmt_value(value), ' ' * 8).lstrip())
            if desc:
                lines.append(f'        ↳ {desc}')
    lines.append('  Output : ' + _indent(fmt_value(output), ' ' * 11).lstrip())
    if output_desc:
        lines.append(f'        ↳ {output_desc}')
    if note:
        lines.append(f'  Ghi chú: {note}')
    log.info('\n'.join(lines))
