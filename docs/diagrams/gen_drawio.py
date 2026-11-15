# -*- coding: utf-8 -*-
"""Sinh file draw.io mô tả luồng Benchmark BIRD + luồng Text-to-SQL (ClubQuery)."""
import math
import re
import sys
from xml.sax.saxutils import quoteattr

OUT = sys.argv[1]

# ---------------------------------------------------------------- styles
S_FN = ("rounded=1;arcSize=4;whiteSpace=wrap;html=1;align=left;verticalAlign=top;spacing=10;"
        "fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=12;")
S_FN_EVAL = S_FN.replace("#dae8fc", "#e1d5e7").replace("#6c8ebf", "#9673a6")
S_FN_APP = S_FN.replace("#dae8fc", "#d5e8d4").replace("#6c8ebf", "#82b366")
S_FN_LLM = S_FN.replace("#dae8fc", "#ffe6cc").replace("#6c8ebf", "#d79b00")
S_FN_GUARD = S_FN.replace("#dae8fc", "#f8cecc").replace("#6c8ebf", "#b85450")
S_DATA = ("shape=document;whiteSpace=wrap;html=1;boundedLbl=1;align=left;verticalAlign=top;spacing=10;"
          "fillColor=#fff2cc;strokeColor=#d6b656;fontSize=12;size=0.08;")
S_DB = ("shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;size=12;align=center;"
        "fillColor=#fff2cc;strokeColor=#d6b656;fontSize=12;")
S_NOTE = ("shape=note;whiteSpace=wrap;html=1;align=left;verticalAlign=top;spacing=10;size=14;"
          "fillColor=#f5f5f5;strokeColor=#999999;fontSize=11;")
S_DEC = ("rhombus;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;fontSize=12;fontStyle=1;")
S_TERM = ("rounded=1;arcSize=50;whiteSpace=wrap;html=1;fillColor=#333333;strokeColor=none;"
          "fontColor=#ffffff;fontSize=13;fontStyle=1;")
S_TITLE = "text;html=1;align=left;verticalAlign=top;fontSize=22;fontStyle=1;whiteSpace=wrap;"
S_SUB = "text;html=1;align=left;verticalAlign=top;fontSize=12;fontColor=#555555;whiteSpace=wrap;"
S_GROUP = ("rounded=1;arcSize=2;whiteSpace=wrap;html=1;align=left;verticalAlign=top;spacing=10;"
           "fillColor=none;dashed=1;strokeColor=#888888;fontSize=13;fontStyle=1;fontColor=#555555;")
S_STAGE = ("rounded=1;arcSize=6;whiteSpace=wrap;html=1;align=left;verticalAlign=top;spacing=12;"
           "fontSize=12;")
S_EDGE = ("edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;strokeWidth=1.5;"
          "fontSize=11;labelBackgroundColor=#ffffff;")
S_EDGE_DASH = S_EDGE + "dashed=1;strokeColor=#888888;fontColor=#555555;"

C = lambda s: '<font face="Consolas" color="#1f4e79">' + s + '</font>'          # code
H_IN = '<b><font color="#1a7f37">▶ INPUT</font></b>'
H_DO = '<b><font color="#9a6700">⚙ XỬ LÝ</font></b>'
H_OUT = '<b><font color="#cf222e">◀ OUTPUT</font></b>'


def fn(title, file, inp=None, proc=None, out=None, extra=None):
    s = '<div style="font-size:14px"><b>' + title + '</b></div>'
    if file:
        s += '<font color="#666666"><i>' + file + '</i></font>'
    for head, body in ((H_IN, inp), (H_DO, proc), (H_OUT, out)):
        if body:
            s += '<hr>' + head + '<br>' + body
    if extra:
        s += '<hr>' + extra
    return s


def est_h(html, w):
    t = re.sub(r'<hr\s*/?>', '\n\n', html)
    t = re.sub(r'<br\s*/?>|</div>|</li>|<li>|</tr>', '\n', t)
    t = re.sub(r'<[^>]+>', '', t)
    t = (t.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
          .replace('&nbsp;', ' ').replace('&quot;', '"'))
    cpl = max(10, int((w - 22) / 6.6))
    lines = sum(max(1, math.ceil(len(seg) / cpl)) for seg in t.split('\n'))
    return int(lines * 16.5 + 40)


class Page:
    def __init__(self, name, w=1900, h=2400):
        self.name, self.w, self.h = name, w, h
        self.cells, self.n = [], 0

    def _id(self):
        self.n += 1
        return 'c%d' % self.n

    def node(self, x, y, w, label, style=S_FN, h=None):
        cid = self._id()
        h = h or est_h(label, w)
        self.cells.append(('v', cid, label, style, x, y, w, h))
        return cid, y + h

    def edge(self, s, t, label='', style=S_EDGE, pts=None, exit=None, entry=None):
        st = style
        if exit:
            st += 'exitX=%s;exitY=%s;exitDx=0;exitDy=0;' % exit
        if entry:
            st += 'entryX=%s;entryY=%s;entryDx=0;entryDy=0;' % entry
        cid = self._id()
        self.cells.append(('e', cid, label, st, s, t, pts))
        return cid

    def xml(self, pid):
        out = ['<diagram id="%s" name=%s><mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" guides="1" '
               'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="%d" '
               'pageHeight="%d" math="0" shadow="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
               % (pid, quoteattr(self.name), self.w, self.h)]
        for c in self.cells:
            if c[0] == 'v':
                _, cid, label, style, x, y, w, h = c
                out.append('<mxCell id="%s" value=%s style=%s vertex="1" parent="1">'
                           '<mxGeometry x="%d" y="%d" width="%d" height="%d" as="geometry"/></mxCell>'
                           % (cid, quoteattr(label), quoteattr(style), x, y, w, h))
            else:
                _, cid, label, style, s, t, pts = c
                geo = '<mxGeometry relative="1" as="geometry">'
                if pts:
                    geo += '<Array as="points">' + ''.join('<mxPoint x="%d" y="%d"/>' % p for p in pts) + '</Array>'
                geo += '</mxGeometry>'
                out.append('<mxCell id="%s" value=%s style=%s edge="1" parent="1" source="%s" target="%s">%s</mxCell>'
                           % (cid, quoteattr(label), quoteattr(style), s, t, geo))
        out.append('</root></mxGraphModel></diagram>')
        return ''.join(out)


pages = []

# =====================================================================================
# PAGE 0 — TỔNG QUAN
# =====================================================================================
p = Page('0. Tổng quan', 2300, 1500)
pages.append(p)
p.node(40, 20, 1800, 'TỔNG QUAN: Benchmark BIRD (Text-to-SQL) và ứng dụng ClubQuery', S_TITLE, 40)
p.node(40, 60, 1800, 'Màu: <b>xanh dương</b> = hàm sinh SQL · <b>tím</b> = hàm chấm điểm · <b>cam</b> = gọi LLM · '
       '<b>đỏ</b> = kiểm tra an toàn · <b>xanh lá</b> = ứng dụng web · <b>vàng</b> = dữ liệu/file. '
       'Chi tiết từng hàm (input → xử lý → output) xem các trang 1 → 3.', S_SUB, 30)

st_data = S_STAGE + "fillColor=#fff2cc;strokeColor=#d6b656;"
st_gen = S_STAGE + "fillColor=#dae8fc;strokeColor=#6c8ebf;"
st_eval = S_STAGE + "fillColor=#e1d5e7;strokeColor=#9673a6;"
st_app = S_STAGE + "fillColor=#d5e8d4;strokeColor=#82b366;"

a, _ = p.node(40, 130, 330,
    '<div style="font-size:15px"><b>① CHUẨN BỊ DỮ LIỆU</b></div><i>(trang 1)</i><hr>'
    '• Tải BIRD dev → ' + C('bird/data/') + '<br>'
    '• ' + C('dev.json') + ': 1.534 câu {question_id, db_id, question, evidence, SQL, difficulty}<br>'
    '• ' + C('dev_gold.sql') + ': 1.534 dòng ' + C('SQL\\tdb_id') + '<br>'
    '• ' + C('dev_databases/') + ': 11 CSDL SQLite<br>'
    '• Phân tích: độ khó 925/464/145; 11 db_id; 1.386 câu có evidence, 148 câu rỗng; '
    'phân loại SQL 6 mức; 192 evidence có hàm giả', st_data)

d, _ = p.node(430, 200, 200, 'Cấu hình<br>evidence?', S_DEC, 120)
kw, _ = p.node(690, 130, 270,
    '<b>WITH knowledge</b><br>' + C('knowledge_list[i] = evidence') +
    '<br>Prompt có dòng ' + C('-- External Knowledge: …') + '<br>→ thư mục ' + C('*_output/'), st_gen)
ko, _ = p.node(690, 300, 270,
    '<b>WITHOUT knowledge</b><br>cờ ' + C('--no_knowledge') + ' → ' + C('knowledge_list = [None]*n') +
    '<br>Prompt không có evidence<br>→ thư mục ' + C('*_0_output/'), st_gen)

g, _ = p.node(1020, 130, 360,
    '<div style="font-size:15px"><b>② SINH SQL (benchmark)</b></div><i>(trang 2a)</i> '
    + C('openai_request.py') + ' / ' + C('ollama_request(2).py') + '<hr>'
    'Lặp từng câu i = 0 … 1533:<br>'
    '1. ' + C('decouple_question_schema') + ' → question, db_path, knowledge<br>'
    '2. ' + C('generate_schema_prompt') + ' → CREATE TABLE…<br>'
    '3. ' + C('generate_comment_prompt') + ' → evidence + câu hỏi<br>'
    '4. ' + C('generate_combined_prompts_one') + ' → prompt<br>'
    '5. ' + C('call_openai / call_ollama') + ' → raw text<br>'
    '6. ' + C('extract_sql') + ' → SQL<br>'
    '7. ghép ' + C('SQL + "\\t----- bird -----\\t" + db_id') + '<br>'
    '8. ' + C('generate_sql_file') + ' → predict_dev.json', st_gen)

pj, _ = p.node(1440, 190, 230,
    '<b>predict_dev.json</b><br>{"0": "SELECT …\\t----- bird -----\\tcalifornia_schools", …, "1533": …}'
    '<br>(đủ 1.534 khoá)', S_DATA, 120)

ex, _ = p.node(1730, 110, 330,
    '<div style="font-size:15px"><b>③ CHẤM EX</b></div><i>(trang 2b)</i> ' + C('evaluation.py') + '<hr>'
    'Chạy predicted SQL và gold SQL trên cùng CSDL;<br>'
    + C('set(pred_rows) == set(gold_rows)') + ' → 1/0<br>'
    'EX = 100 × Σ đúng / N (theo simple / moderate / challenging / total)', st_eval)
ve, _ = p.node(1730, 300, 330,
    '<div style="font-size:15px"><b>③ CHẤM VES</b></div><i>(trang 2c)</i> ' + C('evaluation_ves.py') + '<hr>'
    'Câu đúng → chạy lại ' + C('iterate_num') + ' lần, R = t_gold / t_pred;<br>'
    'VES = 100 × Σ √R / N (câu sai R = 0)', st_eval)

res, _ = p.node(1440, 520, 620,
    '<div style="font-size:15px"><b>④ BẢNG KẾT QUẢ</b></div><i>(trang 2d)</i><hr>'
    'Lặp cho mỗi model ∈ {GPT-3.5-Turbo (paper), DeepSeek-Coder-V2, Qwen2.5-Coder, Gemma3, …} × {with, without}:<br>'
    '→ 2 file predict_dev.json → 4 con số: <b>EX w/ KG · EX w/o KG · VES w/ KG · VES w/o KG</b>', st_eval)

p.edge(a, d, 'question, evidence,<br>db_id, db_path')
p.edge(d, kw, 'có evidence', exit=('0.5', '0'), entry=('0', '0.5'))
p.edge(d, ko, 'không', exit=('0.5', '1'), entry=('0', '0.5'))
p.edge(kw, g, '', entry=('0', '0.3'))
p.edge(ko, g, '', entry=('0', '0.7'))
p.edge(g, pj, '1.534 SQL')
p.edge(pj, ex, '', entry=('0', '0.5'))
p.edge(pj, ve, '', entry=('0', '0.5'))
p.edge(ex, res, 'EX', exit=('1', '0.5'), entry=('1', '0.3'), pts=[(2100, 190), (2100, 560)])
p.edge(ve, res, 'VES', exit=('0.5', '1'), entry=('0.75', '0'))
p.edge(a, ex, 'dev_gold.sql + difficulty (dev.json)', S_EDGE_DASH, exit=('0.5', '0'), entry=('0.5', '0'),
       pts=[(205, 100), (1895, 100)])

# ---- luồng text-to-sql (tóm tắt)
p.node(40, 720, 2020, '<div style="font-size:15px"><b>⑤ LUỒNG TEXT-TO-SQL (ứng dụng ClubQuery) — trang 3</b></div>'
       'Cùng lõi "dựng prompt → gọi LLM → extract_sql" với benchmark; khác ở chỗ: không ghi predict_dev.json mà '
       '<b>kiểm tra an toàn → chạy SQL chỉ đọc → sinh câu trả lời tiếng Việt → so với gold (nếu là câu dev) → ghi log → hiển thị UI</b>.',
       S_GROUP, 640)
y0 = 820
w = 220
xs = [70, 330, 590, 850, 1110, 1370, 1630]
labels = [
    '<b>UI (app.js)</b><br>Người dùng gõ câu hỏi / chọn câu dev, model, tick evidence, từ điển → ' + C('POST /api/ask'),
    '<b>main.ask</b> + ' + C('current_user') + '<br>xác thực token, lấy role → ' + C('service.ask'),
    '<b>Ghép knowledge</b><br>evidence câu dev / evidence tự nhập + ' + C('match_glossary') + ' → ' + C('normalize_pseudo_sql'),
    '<b>prompt.build_prompt</b><br>schema đã lọc theo role + comment + "Respond … ```sql"',
    '<b>llm.generate_sql</b><br>' + C('complete()') + ' (OpenAI-compatible: OpenAI/Groq/Ollama) → ' + C('extract_sql'),
    '<b>guard.check_select</b><br>1 câu, chỉ SELECT/WITH<br><b>guard.execute</b><br>read-only + authorizer + timeout 10s',
    '<b>answer.make_answer</b><br>LLM trả lời 1–3 câu tiếng Việt (hoặc template)',
]
styles = [S_FN_APP, S_FN_APP, S_FN_APP, S_FN, S_FN_LLM, S_FN_GUARD, S_FN_LLM]
ids = []
for i in range(7):
    cid, _ = p.node(xs[i], y0, w, labels[i], styles[i], 150)
    ids.append(cid)
for i in range(6):
    p.edge(ids[i], ids[i + 1])
cmp_, _ = p.node(1630, 1030, 220, '<b>So với gold</b> (nếu là câu dev)<br>chạy gold SQL quyền admin → '
                 + C('same_result = set(rows)==set(gold_rows)') + ' → is_correct', S_FN_EVAL, 130)
log, _ = p.node(1370, 1030, 220, '<b>Ghi query_log</b><br>câu hỏi, SQL, trạng thái, latency, is_correct…', S_FN_APP, 130)
ui2, _ = p.node(1110, 1030, 220, '<b>UI renderResult()</b><br>SQL · bảng kết quả · câu trả lời · evidence đã dùng · '
                'gold SQL + Đúng/Sai · trạng thái', S_FN_APP, 130)
p.edge(ids[6], cmp_, '')
p.edge(cmp_, log, '')
p.edge(log, ui2, 'JSON')
p.edge(g, ids[3], 'dùng chung cấu trúc prompt', S_EDGE_DASH, exit=('0.5', '1'), entry=('0.5', '0'),
       pts=[(1200, 790), (960, 790)])

# =====================================================================================
# PAGE 1 — CHUẨN BỊ DỮ LIỆU
# =====================================================================================
p = Page('1. Chuẩn bị dữ liệu', 1900, 1700)
pages.append(p)
p.node(40, 20, 1700, '① CHUẨN BỊ DỮ LIỆU — tải và phân tích tập BIRD dev', S_TITLE, 40)
p.node(40, 60, 1700, 'Mục tiêu: có đủ câu hỏi + evidence + CSDL để sinh SQL, và đáp án gold + độ khó để chấm. '
       'Không sửa dev.json / CSDL (giữ nguyên để so sánh công bằng với paper).', S_SUB, 30)

dl, y = p.node(40, 110, 400, fn('Tải BIRD dev set', 'bird-bench.github.io → dev.zip (bản dev_20240627)',
    'Link tải bộ dev của BIRD',
    'Giải nén vào ' + C('src/DAMO-ConvAI/bird/data/') + '; giải nén tiếp ' + C('dev_databases.zip'),
    'Thư mục ' + C('bird/data/') + ' gồm 4 thành phần (bên phải)'), S_FN_APP)

f1, _ = p.node(520, 110, 380,
    '<b>dev.json</b> — 1.534 phần tử<br>'
    + C('{<br>&nbsp;"question_id": 1379,<br>&nbsp;"db_id": "student_club",<br>'
        '&nbsp;"question": "How many meeting events were held in 2020?",<br>'
        '&nbsp;"evidence": "meeting events refers to type = \'Meeting\'; held in 2020 refers to YEAR(event_date) = 2020",<br>'
        '&nbsp;"SQL": "SELECT COUNT(event_id) FROM event WHERE …",<br>&nbsp;"difficulty": "simple"<br>}'), S_DATA)
f2, _ = p.node(960, 110, 360,
    '<b>dev_gold.sql</b> — 1.534 dòng<br>Mỗi dòng: ' + C('&lt;gold SQL&gt;\\t&lt;db_id&gt;') +
    '<br>Dòng i ↔ dev.json[i] ↔ khoá "i" trong predict_dev.json<br>(nằm ở ' + C('bird/llm/data/dev_gold.sql') + ')', S_DATA)
f3, _ = p.node(960, 290, 360, '<b>dev_databases/</b> — 11 CSDL SQLite<br>'
    + C('&lt;db_root&gt;/&lt;db_id&gt;/&lt;db_id&gt;.sqlite') +
    '<br>+ ' + C('database_description/*.csv') + ' (mô tả cột – prompt KHÔNG dùng)', S_DB, 120)
f4, _ = p.node(1380, 110, 300, '<b>dev_tables.json</b><br>schema dạng JSON (tên bảng, cột, khoá) – tham khảo, '
    'luồng benchmark lấy schema trực tiếp từ sqlite_master', S_DATA, 120)
for f in (f1, f2, f3, f4):
    p.edge(dl, f, '')

an, y = p.node(40, 520, 560, fn('Phân tích dev set', 'notebook / script Python (json + collections.Counter)',
    C('dev.json') + ', ' + C('dev_gold.sql'),
    '• Đếm số câu, đếm theo ' + C('difficulty') + ', theo ' + C('db_id') + '<br>'
    '• Đếm câu có / không có evidence<br>'
    '• Kiểm tra dev_gold.sql khớp thứ tự với dev.json<br>'
    '• Phân loại SQL đáp án 6 mức: ' + C('app/scripts/sql_category.py: classify(sql)') + '<br>'
    '• Quét evidence chứa hàm giả (DIVIDE, SUBTRACT, YEAR…): ' + C('evidence_norm.py'),
    'Bảng thống kê (bên phải) → làm căn cứ thiết kế thí nghiệm'), S_FN_APP)
p.edge(f1, an, 'đọc', exit=('0.5', '1'), entry=('0.5', '0'))

stt, _ = p.node(680, 520, 520,
    '<b>KẾT QUẢ PHÂN TÍCH</b><hr>'
    '<b>Tổng:</b> 1.534 câu, 11 CSDL<br>'
    '<b>Độ khó:</b> simple 925 · moderate 464 · challenging 145<br>'
    '<b>Theo db_id:</b> card_games 191 · codebase_community 186 · formula_1 174 · thrombosis_prediction 163 · '
    'student_club 158 · toxicology 145 · superhero 129 · european_football_2 129 · financial 106 · '
    'california_schools 89 · debit_card_specializing 64<br>'
    '<b>Evidence:</b> 1.386 câu có, 148 câu rỗng (với 148 câu này "with" và "without" cho prompt giống nhau)<br>'
    '<b>Hàm giả trong evidence:</b> 192 evidence; 182 đổi được bằng ' + C('normalize_pseudo_sql') + '; 21 sai cú pháp', S_NOTE)
p.edge(an, stt, '')

cat, _ = p.node(1260, 520, 480, fn('classify(sql)', 'app/scripts/sql_category.py',
    'Gold SQL của 1 câu',
    'Tách token, gắn nhãn:<br>1 SINGLE_TABLE · 2 JOIN · 3 SET_OP · 4 OUTER_JOIN · 5 GROUP_BY · 6 DIVISION · (phụ) NESTED',
    C("{'tags': [...], 'level': max mức, 'tables': [...], 'nested': bool}") +
    '<br>→ dùng ở ' + C('ex_ves_by_category.py') + ' để chấm EX/VES theo từng mức'), S_FN_EVAL)
p.edge(stt, cat, '')

use, _ = p.node(40, 900, 1700,
    '<b>DỮ LIỆU ĐI VÀO CÁC BƯỚC SAU</b><hr>'
    '• ' + C('question') + ', ' + C('evidence') + ', ' + C('db_id') + ' (dev.json) → <b>② Sinh SQL</b> '
    '(' + C('decouple_question_schema') + ')<br>'
    '• ' + C('dev_databases/&lt;db_id&gt;/&lt;db_id&gt;.sqlite') + ' → ② (đọc CREATE TABLE) và ③ (chạy SQL để chấm)<br>'
    '• ' + C('dev_gold.sql') + ' → <b>③ Chấm EX/VES</b> (' + C("package_sqls(mode='gt')") + ')<br>'
    '• ' + C('difficulty') + ' (dev.json, tham số ' + C('--diff_json_path') + ') → ③ chia điểm simple/moderate/challenging<br>'
    '• 158 câu student_club (question_id 1312–1469) → nạp vào ' + C('app.sqlite / dev_question') + ' cho <b>⑤ ClubQuery</b>',
    S_NOTE)
p.edge(an, use, '', exit=('0.5', '1'), entry=('0.15', '0'))

# =====================================================================================
# PAGE 2a — SINH SQL
# =====================================================================================
p = Page("2a. Benchmark - Sinh SQL", 2000, 4300)
pages.append(p)
p.node(40, 20, 1900, '② LUỒNG BENCHMARK — Sinh SQL cho 1.534 câu → predict_dev.json', S_TITLE, 40)
p.node(40, 60, 1900, 'Script: ' + C('bird/llm/src/openai_request.py') + ' (GPT-3.5, bám sát ' + C('gpt_request.py') +
       ' gốc của paper) · ' + C('ollama_request.py') + ' / ' + C('ollama_request2.py') +
       ' (DeepSeek, Qwen, Gemma… chạy local qua Ollama trên Kaggle). Cột trái = chuỗi hàm; cột phải = ví dụ câu 1379.',
       S_SUB, 30)
W = 760
X = 40
XR = 900

n0, y = p.node(X, 110, W, fn('Bước 0. Chạy lệnh — main (argparse)', 'openai_request.py / ollama_request2.py',
    C('python src/openai_request.py --model gpt-3.5-turbo [--no_knowledge] [--cot] '
      '--eval_path ../data/dev.json --db_root_path ../data/dev_databases/ '
      '--data_output_path ./exp_result/openai_output/predict_dev.json [--limit N]') + '<br>'
    '• ' + C('--model') + ': tên model API hoặc tag Ollama (' + C('qwen2.5-coder:7b') + ', ' + C('deepseek-coder-v2:16b') + ', ' + C('gemma3:12b') + ')<br>'
    '• ' + C('--no_knowledge') + ': chạy WITHOUT knowledge (bản ollama: dùng ' + C('ollama_request2.py') + ')<br>'
    '• ' + C('--normalize_evidence') + ' (bản *2): chuẩn hoá hàm giả trong evidence · ' + C('--ids_file') + ': chỉ chạy 1 số câu',
    'Đọc tham số; nạp ' + C('OPEN_AI_KEY') + ' từ .env, tạo ' + C('client = OpenAI(api_key)') + ' (bản Ollama: URL ' + C('http://localhost:11434/api/chat') + ')',
    C('args') + ', ' + C('client')), S_FN)

n1, y = p.node(X, y + 50, W, fn('Bước 1a. Đọc dev.json — json.load(open(eval_path))', 'main',
    C('args.eval_path') + ' = ../data/dev.json',
    'Đọc file JSON; nếu có ' + C('--limit N') + ' → lấy N câu đầu',
    C('eval_data') + ': list 1.534 dict {question_id, db_id, question, evidence, SQL, difficulty}'), S_FN)
p.edge(n0, n1, 'eval_path')

n2, y = p.node(X, y + 50, W, fn('Bước 1b. Tách dữ liệu — decouple_question_schema(datasets, db_root_path)', 'openai_request.py / ollama_request.py',
    C('datasets') + ' = eval_data · ' + C('db_root_path') + ' = ../data/dev_databases/',
    'Duyệt từng phần tử, tách thành 3 list song song (cùng thứ tự với dev.json):<br>'
    + C("question_list.append(data['question'])") + '<br>'
    + C("db_path_list.append(os.path.join(db_root_path, db_id, db_id + '.sqlite'))") + '<br>'
    + C("knowledge_list.append(data['evidence'])"),
    C('question_list, db_path_list, knowledge_list') + ' (mỗi list 1.534 phần tử; assert độ dài bằng nhau)'), S_FN)
p.edge(n1, n2, 'eval_data')

dec, y = p.node(X + 230, y + 50, 300, 'Bước 1c.<br>--no_knowledge ?', S_DEC, 100)
p.edge(n2, dec, 'knowledge_list')
kwb, _ = p.node(X, y + 40, 360, '<b>WITH knowledge</b> (mặc định)<br>giữ ' + C('knowledge_list[i] = evidence') +
                '<br>[bản *2 + ' + C('--normalize_evidence') + ']: ' + C('knowledge = normalize_pseudo_sql(knowledge)') +
                '<br>VD: ' + C('YEAR(event_date)') + ' → ' + C("CAST(STRFTIME('%Y', event_date) AS INTEGER)") +
                '<br>→ output: ' + C('exp_result/&lt;model&gt;_output/'), S_FN)
kob, y2 = p.node(X + 400, y + 40, 360, '<b>WITHOUT knowledge</b><br>' + C('knowledge_list = [None] * len(question_list)') +
                 '<br>Prompt sẽ không có dòng External Knowledge, model phải tự đoán ánh xạ từ ngữ → cột/giá trị'
                 '<br>→ output: ' + C('exp_result/&lt;model&gt;_0_output/'), S_FN)
p.edge(dec, kwb, 'Không có cờ', exit=('0', '0.5'), entry=('0.5', '0'))
p.edge(dec, kob, 'Có cờ', exit=('1', '0.5'), entry=('0.5', '0'))
y = max(y2, y + 40 + est_h('x' * 400, 360)) + 40

loop_top = y
n3, y = p.node(X + 20, y + 40, W - 40, fn('Vòng lặp: collect_response(client, model, db_path_list, question_list, knowledge_list, output_path, checkpoint_every=50, cot=False)',
    'vòng lặp chính',
    '3 list ở trên + client/model; ' + C('output_path') + ' để ghi checkpoint; ' + C('cot') + ' = dùng prompt Chain-of-Thought',
    C('for i, question in enumerate(tqdm(question_list)):') + ' → với mỗi câu gọi lần lượt bước 2 → 7 bên dưới; '
    'bọc trong ' + C('try/except') + ': lỗi bất kỳ (mạng, hết retry) → ' + C('sql = "SELECT"') + ' (câu đó chắc chắn bị chấm sai) và chạy tiếp',
    C('response_list') + ': list 1.534 chuỗi'), S_FN)
p.edge(kwb, n3, '', entry=('0.3', '0'))
p.edge(kob, n3, '', entry=('0.7', '0'))

n41, y = p.node(X + 40, y + 40, W - 80, fn('Bước 2. Lấy cấu trúc bảng — generate_schema_prompt(db_path)', '',
    C('db_path_list[i]') + ' — VD ' + C('../data/dev_databases/student_club/student_club.sqlite'),
    C('sqlite3.connect(db_path)') + ' → ' + C("SELECT name FROM sqlite_master WHERE type='table'") +
    ' → với mỗi bảng (bỏ ' + C('sqlite_sequence') + '): ' + C("SELECT sql FROM sqlite_master WHERE name=…") +
    ' lấy câu CREATE TABLE gốc → nối bằng ' + C("'\\n\\n'") + '. Không kèm dòng dữ liệu mẫu (num_rows=None).',
    C('schema_prompt') + ': chuỗi các câu CREATE TABLE (student_club: 8 bảng ≈ 2.300 ký tự)'), S_FN)
p.edge(n3, n41, 'db_path_list[i]')

n42, y = p.node(X + 40, y + 40, W - 80, fn('Bước 3. Viết đề bài (+ evidence) — generate_comment_prompt(question, knowledge)', '',
    C('question_list[i]') + ', ' + C('knowledge_list[i]') + ' (chuỗi evidence hoặc None)',
    '<b>knowledge rỗng/None</b> → ' + C('"-- Using valid SQLite, answer the following questions for the tables provided above.\\n-- &lt;question&gt;"') + '<br>'
    '<b>có knowledge</b> → ' + C('"-- External Knowledge: &lt;evidence&gt;\\n-- Using valid SQLite and understading External Knowledge, answer the following questions for the tables provided above.\\n-- &lt;question&gt;"'),
    C('comment_prompt')), S_FN)
p.edge(n41, n42, '')

n43, y = p.node(X + 40, y + 40, W - 80, fn('Bước 4. Ghép prompt — generate_combined_prompts_one(db_path, question, knowledge)', '',
    C('schema_prompt') + ' (bước 2), ' + C('comment_prompt') + ' (bước 3)',
    'Ghép chuỗi, phần đuôi khác nhau theo script:<br>'
    '• ' + C('openai_request.py') + ': ' + C("schema + '\\n\\n' + comment + '\\nGenerate the SQL after thinking step by step: ' + '\\nSELECT '") + ' (đúng như gpt_request.py gốc)<br>'
    '• ' + C('ollama_request.py') + ': ' + C("schema + '\\n\\n' + comment + '\\nRespond with the final SQLite query only, inside a ```sql code block. Do not add any explanation.'") + '<br>'
    '• ' + C('--cot') + ': ' + C('generate_combined_prompts_cot') + ' = 1-shot ví dụ (few_shot / few_shot_no_kg) + schema + comment',
    C('prompt') + ' (string)'), S_FN)
p.edge(n42, n43, '')

n44, y = p.node(X + 40, y + 40, W - 80, fn('Bước 5. Gọi LLM — call_openai(client, model, prompt, max_retries=5, max_tokens=256)  /  call_ollama(model, prompt, max_retries=3, timeout=120)', '',
    C('prompt') + ', ' + C('model'),
    '<b>OpenAI:</b> ' + C("client.chat.completions.create(model, messages=[{'role':'user','content':prompt}], temperature=0, max_tokens=256, stop=['--','\\n\\n',';','#'])") +
    '; lỗi 429 (rate limit) → chờ rồi thử lại ≤ 5 lần<br>'
    '<b>Ollama:</b> ' + C("requests.post(OLLAMA_URL, json={model, messages, stream: False, options:{temperature:0}}, timeout=120)") +
    '; lỗi → chờ 3s, thử lại ≤ 3 lần<br>'
    'temperature=0 → luôn chọn token xác suất cao nhất → kết quả lặp lại được',
    C('raw') + ': chuỗi model trả về (có thể kèm ```sql …```, &lt;think&gt;…&lt;/think&gt;, giải thích)'), S_FN_LLM)
p.edge(n43, n44, 'prompt')

n45, y = p.node(X + 40, y + 40, W - 80, fn('Bước 6. Tách SQL — extract_sql(raw)', '',
    C('raw'),
    '<b>Ollama:</b> xoá ' + C('&lt;think&gt;…&lt;/think&gt;') + ' → lấy nội dung khối ' + C('```sql … ```') +
    ' (không có thì bỏ fence mở) → cắt tại dấu ' + C(';') + ' đầu tiên → strip<br>'
    '<b>OpenAI:</b> như trên, rồi bỏ ' + C('SELECT') + ' ở đầu (nếu có) và thêm lại ' + C("'SELECT '") +
    ' — mô phỏng code gốc ' + C("'SELECT' + completion_text") + '<br>'
    '<b>--cot:</b> ' + C('extract_sql_cot') + ' tách theo mốc ' + C("': SELECT'") + '<br>'
    'Rỗng → trả ' + C('"SELECT"'),
    C('sql') + ' — 1 câu SQL sạch, không dấu ;'), S_FN)
p.edge(n44, n45, 'raw')

n46, y = p.node(X + 40, y + 40, W - 80, fn('Bước 7. Gắn tên CSDL + checkpoint', '',
    C('sql') + ', ' + C('db_id = basename(db_path).replace(".sqlite","")'),
    C("response_list.append(sql + '\\t----- bird -----\\t' + db_id)") +
    ' — chuỗi phân cách này để ' + C('package_sqls') + ' ở bước chấm tách lại (sql, db_name)<br>'
    'Cứ ' + C('(i+1) % 50 == 0') + ' → ghi tạm ' + C('generate_sql_file') + ' (phòng mất phiên Kaggle)',
    '1 phần tử của ' + C('response_list') + ' → quay lại vòng lặp với câu i+1'), S_FN)
p.edge(n45, n46, 'sql')
p.edge(n46, n3, 'i += 1 (đến khi i = 1533)', S_EDGE_DASH, exit=('0', '0.5'), entry=('0', '0.5'),
       pts=[(X, y - 60), (X, loop_top + 90)])
p.node(X, loop_top, W, 'VÒNG LẶP — mỗi câu hỏi i = 0 … 1533', S_GROUP, y - loop_top + 20)

n5, y = p.node(X, y + 70, W, fn('Bước 8. Ghi file — generate_sql_file(sql_lst, output_path)', '',
    C('response_list') + ' (đủ 1.534 phần tử), ' + C('args.data_output_path'),
    C('result = {i: sql for i, sql in enumerate(sql_lst)}') + '; tạo thư mục nếu chưa có; ' + C('json.dump(result, indent=4)'),
    'file ' + C('predict_dev.json')), S_FN)
p.edge(n46, n5, 'hết vòng lặp', exit=('0.5', '1'), entry=('0.5', '0'))

pj, y = p.node(X + 130, y + 40, 500, '<b>predict_dev.json</b><br>' + C(
    '{<br>&nbsp;"0": "SELECT … \\t----- bird -----\\tcalifornia_schools",<br>&nbsp;…<br>'
    '&nbsp;"1379": "SELECT COUNT(*) FROM event WHERE type = \'Meeting\' AND STRFTIME(\'%Y\', event_date) = \'2020\'\\t----- bird -----\\tstudent_club",<br>'
    '&nbsp;…<br>&nbsp;"1533": "…"<br>}') + '<br>Khoá = chỉ số câu trong dev.json → sang ③ chấm EX / VES', S_DATA)
p.edge(n5, pj, '')

# ---- cột ví dụ
ex_y = 110
e1, ex_y = p.node(XR, ex_y, 560, '<b>VÍ DỤ: câu 1379 (student_club, simple)</b><hr>'
    '<b>Sau decouple_question_schema:</b><br>'
    'question = ' + C('How many meeting events were held in 2020?') + '<br>'
    'db_path = ' + C('../data/dev_databases/student_club/student_club.sqlite') + '<br>'
    'knowledge = ' + C("meeting events refers to type = 'Meeting'; held in 2020 refers to YEAR(event_date) = 2020"), S_NOTE)
e2, ex_y = p.node(XR, ex_y + 30, 560, '<b>schema_prompt (bước 2) — trích</b><br>' + C(
    'CREATE TABLE event (<br>&nbsp;event_id TEXT constraint event_pk primary key,<br>&nbsp;event_name TEXT, event_date TEXT,'
    ' type TEXT, notes TEXT, location TEXT, status TEXT)<br><br>CREATE TABLE major (…)<br>… (8 bảng: event, major, zip_code, '
    'attendance, budget, expense, income, member)'), S_NOTE)
e3, ex_y = p.node(XR, ex_y + 30, 560, '<b>Đuôi prompt — WITH knowledge</b> (ollama_request.py)<br>' + C(
    '-- External Knowledge: meeting events refers to type = \'Meeting\'; held in 2020 refers to YEAR(event_date) = 2020<br>'
    '-- Using valid SQLite and understading External Knowledge, answer the following questions for the tables provided above.<br>'
    '-- How many meeting events were held in 2020?<br>Respond with the final SQLite query only, inside a ```sql code block. Do not add any explanation.'), S_NOTE)
e4, ex_y = p.node(XR, ex_y + 30, 560, '<b>Đuôi prompt — WITHOUT knowledge</b><br>' + C(
    '-- Using valid SQLite, answer the following questions for the tables provided above.<br>'
    '-- How many meeting events were held in 2020?<br>Respond with the final SQLite query only, …') +
    '<br>→ model phải tự đoán "meeting events" ↔ cột ' + C('type') + ' = ' + C("'Meeting'"), S_NOTE)
e5, ex_y = p.node(XR, ex_y + 30, 560, '<b>Đuôi prompt — openai_request.py (paper)</b><br>' + C(
    '… -- How many meeting events were held in 2020?<br>Generate the SQL after thinking step by step: <br>SELECT '), S_NOTE)
e6, ex_y = p.node(XR, ex_y + 30, 560, '<b>raw (bước 5)</b> — minh hoạ<br>' + C(
    '```sql<br>SELECT COUNT(*) FROM event WHERE type = \'Meeting\' AND STRFTIME(\'%Y\', event_date) = \'2020\';<br>```') +
    '<hr><b>sql (bước 6)</b><br>' + C("SELECT COUNT(*) FROM event WHERE type = 'Meeting' AND STRFTIME('%Y', event_date) = '2020'") +
    '<hr><b>chuỗi lưu (bước 7)</b><br>' + C('"…= \'2020\'\\t----- bird -----\\tstudent_club"'), S_NOTE)
p.edge(n2, e1, '', S_EDGE_DASH)
p.edge(n41, e2, '', S_EDGE_DASH)
p.edge(n43, e3, '', S_EDGE_DASH, exit=('1', '0.3'), entry=('0', '0.5'))
p.edge(n45, e6, '', S_EDGE_DASH)

e7, ex_y = p.node(XR, ex_y + 60, 560, '<b>BẢNG THAM SỐ GỌI LLM</b><hr>'
    '<table border="1" cellpadding="3" style="border-collapse:collapse;font-size:11px">'
    '<tr><th>Tham số</th><th>OpenAI</th><th>Ollama</th><th>Ý nghĩa</th></tr>'
    '<tr><td>temperature</td><td>0</td><td>0</td><td>tất định</td></tr>'
    '<tr><td>max_tokens</td><td>256 (CoT 1024)</td><td>mặc định</td><td>giới hạn độ dài (như paper)</td></tr>'
    '<tr><td>stop</td><td>-- , \\n\\n , ; , #</td><td>—</td><td>dừng khi hết câu SQL (như paper)</td></tr>'
    '<tr><td>retry</td><td>5 (lỗi 429)</td><td>3 (chờ 3s)</td><td>chống lỗi mạng/rate limit</td></tr>'
    '<tr><td>timeout</td><td>—</td><td>120 s</td><td>mỗi lần gọi</td></tr></table>', S_NOTE, 270)

# =====================================================================================
# PAGE 2b — EX
# =====================================================================================
def eval_page(name, title, script, is_ves):
    p = Page(name, 2000, 3200)
    pages.append(p)
    p.node(40, 20, 1900, title, S_TITLE, 40)
    p.node(40, 60, 1900, 'Script gốc của BIRD, không sửa (' + C('bird/llm/src/' + script) + '). '
           'Chạy 2 lần cho mỗi model: thư mục ' + C('*_output/') + ' → <b>' + ('VES' if is_ves else 'EX') +
           ' with knowledge</b>; thư mục ' + C('*_0_output/') + ' → <b>' + ('VES' if is_ves else 'EX') + ' without knowledge</b>.',
           S_SUB, 30)
    X, W, XR = 40, 800, 920
    cli = ('python src/' + script + ' --predicted_sql_path ./exp_result/openai_output/ --ground_truth_path ./data/ '
           '--data_mode dev --db_root_path ../data/dev_databases/ --diff_json_path ../data/dev.json '
           '--num_cpus 8 --meta_time_out 30.0' + (' --iterate_num 5' if is_ves else ''))
    params = ('• ' + C('--predicted_sql_path') + ': thư mục chứa predict_dev.json (phải có / cuối vì code nối chuỗi)<br>'
              '• ' + C('--ground_truth_path') + ': thư mục chứa dev_gold.sql<br>'
              '• ' + C('--data_mode dev') + ': ghép tên file ' + C('predict_dev.json') + ', ' + C('dev_gold.sql') + '<br>'
              '• ' + C('--db_root_path') + ': thư mục 11 CSDL<br>'
              '• ' + C('--diff_json_path') + ': dev.json — chỉ để lấy ' + C('difficulty') + '<br>'
              '• ' + C('--num_cpus') + ': số tiến trình song song · ' + C('--meta_time_out') + ': giây tối đa/câu<br>'
              '• ' + C('--mode_predict gpt') + ' / ' + C('--mode_gt gt') + ': cách đọc file')
    if is_ves:
        params += '<br>• ' + C('--iterate_num 5') + ': số lần chạy lại mỗi câu để đo thời gian (paper dùng 5; phải ≥ 2)'
    n0, y = p.node(X, 110, W, fn('Bước 1. Chạy lệnh — main (argparse)', script, C(cli) + '<br>' + params,
                                 'Khởi tạo biến toàn cục ' + C('exec_result = []'), C('args')), S_FN_EVAL)
    a1, ya = p.node(X, y + 50, 380, fn("Bước 2a. package_sqls(predicted_sql_path, db_root_path, mode='gpt', data_mode='dev')", '',
        C('predict_dev.json'),
        'Với mỗi (idx, sql_str): ' + C("sql, db_name = sql_str.split('\\t----- bird -----\\t')") +
        '; nếu giá trị không phải str → (" ", "financial"); ' + C("db_path = db_root_path + db_name + '/' + db_name + '.sqlite'"),
        C('pred_queries') + ' (1.534 SQL), ' + C('db_paths')), S_FN_EVAL)
    a2, yb = p.node(X + 420, y + 50, 380, fn("Bước 2b. package_sqls(ground_truth_path, db_root_path, mode='gt', data_mode='dev')", '',
        C('dev_gold.sql'),
        'Đọc từng dòng: ' + C("sql, db_name = line.strip().split('\\t')"),
        C('gt_queries') + ' (1.534 SQL), ' + C('db_paths_gt') + ' (không dùng)'), S_FN_EVAL)
    p.edge(n0, a1, '')
    p.edge(n0, a2, '')
    y = max(ya, yb)
    z, y = p.node(X + 200, y + 50, 400, fn('Bước 3. query_pairs = list(zip(pred_queries, gt_queries))', '', None,
        'Ghép cặp theo chỉ số i', C('[(pred_0, gold_0), …, (pred_1533, gold_1533)]')), S_FN_EVAL)
    p.edge(a1, z, '')
    p.edge(a2, z, '')
    if is_ves:
        rp = fn('Bước 4–6. run_sqls_parallel(sqls, db_places, num_cpus, iterate_num, meta_time_out)', '',
                C('query_pairs') + ', ' + C('db_paths') + ' (của pred), ' + C('num_cpus') + ', ' + C('iterate_num') + ', ' + C('meta_time_out'),
                C('pool = mp.Pool(num_cpus)') + '; với mỗi cặp i: ' +
                C('pool.apply_async(execute_model, args=(pred, gold, db_paths[i], i, iterate_num, meta_time_out), callback=result_callback)') +
                '; ' + C('pool.close(); pool.join()'),
                'Không trả về; ' + C('result_callback') + ' append từng kết quả vào ' + C('exec_result') + ' (thứ tự lộn xộn)')
    else:
        rp = fn('Bước 4–5. run_sqls_parallel(sqls, db_places, num_cpus, meta_time_out)', '',
                C('query_pairs') + ', ' + C('db_paths') + ' (của pred), ' + C('num_cpus') + ', ' + C('meta_time_out'),
                C('pool = mp.Pool(num_cpus)') + '; với mỗi cặp i: ' +
                C('pool.apply_async(execute_model, args=(pred, gold, db_paths[i], i, meta_time_out), callback=result_callback)') +
                '; ' + C('pool.close(); pool.join()'),
                'Không trả về; ' + C('result_callback') + ' append từng kết quả vào ' + C('exec_result') + ' (thứ tự lộn xộn)')
    r, y = p.node(X, y + 50, W, rp, S_FN_EVAL)
    p.edge(z, r, 'query_pairs')
    top = y + 20
    if is_ves:
        m, y = p.node(X + 30, y + 60, W - 60, fn('Bước 4. execute_model(predicted_sql, ground_truth, db_place, idx, iterate_num, meta_time_out)',
            'chạy trong 1 tiến trình con', 'cặp SQL thứ idx + đường dẫn CSDL',
            C('time_ratio = func_timeout(meta_time_out * iterate_num, iterated_execute_sql, args=(…))') + '<br>'
            'Hết giờ (' + C('FunctionTimedOut') + ') → ' + C('time_ratio = 0') + '; SQL lỗi (Exception) → ' + C('time_ratio = 0'),
            C("{'sql_idx': idx, 'time_ratio': số thực ≥ 0}")), S_FN_EVAL)
        it, y = p.node(X + 60, y + 40, W - 120, fn('Bước 4–6. iterated_execute_sql(predicted_sql, ground_truth, db_path, iterate_num)', '',
            'cặp SQL, ' + C('db_path') + ', ' + C('iterate_num'),
            '1. ' + C('sqlite3.connect(db_path)') + '; chạy pred → ' + C('fetchall()') + '; chạy gold → ' + C('fetchall()') + '<br>'
            '2. Nếu ' + C('set(pred_res) != set(gold_res)') + ' → ' + C('time_ratio = 0') + ' (câu sai, không đo thời gian)<br>'
            '3. Nếu đúng: lặp ' + C('iterate_num') + ' lần: ' + C('t_pred = execute_sql(pred)') + ', ' + C('t_gold = execute_sql(gold)') +
            ', ' + C('diff_list.append(t_gold / t_pred)') + '<br>'
            '4. ' + C('processed = clean_abnormal(diff_list)') + '; ' + C('time_ratio = mean(processed)'),
            C('time_ratio') + ' (R > 1: pred nhanh hơn gold; R < 1: chậm hơn)'), S_FN_EVAL)
        es, y = p.node(X + 90, y + 40, 300, fn('Bước 5. execute_sql(sql, db_path)', '', 'một câu SQL',
            C('start = time.time(); cursor.execute(sql); exec_time = time.time() - start'), 'số giây'), S_FN_EVAL)
        ca, _ = p.node(X + 420, y - est_h(fn('Bước 5. execute_sql(sql, db_path)', '', 'một câu SQL',
            C('start = time.time(); cursor.execute(sql); exec_time = time.time() - start'), 'số giây'), 300), 320,
            fn('Bước 6. clean_abnormal(input)', '', C('diff_list') + ' (iterate_num tỉ lệ)',
               'mean, std; giữ x nếu ' + C('mean − 3·std &lt; x &lt; mean + 3·std'), 'list đã lọc ngoại lai'), S_FN_EVAL)
        p.edge(r, m, 'mỗi cặp i (song song)')
        p.edge(m, it, '')
        p.edge(it, es, '×2·iterate_num')
        p.edge(it, ca, '', exit=('0.75', '1'), entry=('0.5', '0'))
    else:
        m, y = p.node(X + 30, y + 60, W - 60, fn('Bước 4. execute_model(predicted_sql, ground_truth, db_place, idx, meta_time_out)',
            'chạy trong 1 tiến trình con', 'cặp SQL thứ idx + đường dẫn CSDL',
            C('res = func_timeout(meta_time_out, execute_sql, args=(predicted_sql, ground_truth, db_place))') + '<br>'
            'Hết giờ (' + C('FunctionTimedOut') + ') → ' + C('res = 0') + '; SQL lỗi cú pháp / sai tên cột (Exception) → ' + C('res = 0'),
            C("{'sql_idx': idx, 'res': 0 | 1}")), S_FN_EVAL)
        es, y = p.node(X + 60, y + 40, W - 120, fn('Bước 5. execute_sql(predicted_sql, ground_truth, db_path)', '',
            'cặp SQL, ' + C('db_path'),
            C('conn = sqlite3.connect(db_path)') + '<br>' + C('cursor.execute(predicted_sql); predicted_res = cursor.fetchall()') + '<br>' +
            C('cursor.execute(ground_truth); ground_truth_res = cursor.fetchall()') + '<br>' +
            C('res = 1 if set(predicted_res) == set(ground_truth_res) else 0') + '<br>'
            '→ so <b>tập</b> các dòng: không xét thứ tự dòng, dòng trùng, tên cột; nhưng thứ tự/số cột trong mỗi dòng phải khớp',
            C('res') + ' ∈ {0, 1}'), S_FN_EVAL)
        p.edge(r, m, 'mỗi cặp i (song song)')
        p.edge(m, es, '')
    p.edge(es if not is_ves else it, r, 'callback → exec_result.append(result)', S_EDGE_DASH,
           exit=('1', '0.5'), entry=('1', '0.5'), pts=[(X + W + 20, y - 40), (X + W + 20, top - 60)])
    p.node(X + 10, top, W - 20, 'MULTIPROCESSING POOL — 1.534 tác vụ', S_GROUP, y - top + 20)
    s, y = p.node(X, y + 60, W, fn(('Bước 7. ' if is_ves else 'Bước 6. ') + 'sort_results(exec_result)', '', C('exec_result') + ' (thứ tự hoàn thành)',
        C("sorted(list, key=lambda x: x['sql_idx'])"), 'list 1.534 kết quả theo đúng thứ tự dev.json'), S_FN_EVAL)
    p.edge(r, s, 'pool.join()', exit=('0', '0.5'), entry=('0', '0.5'), pts=[(20, 0), (20, 0)] and None)
    if is_ves:
        cv, y = p.node(X, y + 40, W, fn('Bước 8. compute_ves_by_diff(exec_results, diff_json_path)  →  compute_ves(results)', '',
            C('exec_result') + ' đã sắp xếp, ' + C('dev.json'),
            'Chia kết quả theo ' + C("content['difficulty']") + ' của dev.json (cùng chỉ số i). Với mỗi nhóm gọi ' + C('compute_ves') + ':<br>'
            + C('total_ratio = Σ sqrt(time_ratio) × 100;  ves = total_ratio / số câu của nhóm'),
            C('simple_ves, moderate_ves, challenging_ves, all_ves, count_lists')), S_FN_EVAL)
        fm = ('<b>CÔNG THỨC VES</b><hr>VES = (1/N) · Σ<sub>n</sub> 𝟙(V̂<sub>n</sub> = V<sub>n</sub>) · √R(Ŷ<sub>n</sub>, Y<sub>n</sub>) × 100<br>'
              'R = trung bình (t_gold / t_pred) sau khi lọc ngoại lai<br><hr>'
              '<b>Đóng góp của 1 câu:</b><br>• sai / lỗi / timeout → 0<br>• đúng, nhanh bằng gold (R=1) → 100<br>'
              '• đúng, nhanh gấp 4 lần (R=4) → 200<br>• đúng, chậm gấp 4 lần (R=0.25) → 50<br><hr>'
              'Lưu ý: phụ thuộc thời gian chạy thực → dao động nhẹ giữa các lần chấm; '
              'VES có thể > EX nếu SQL sinh ra chạy nhanh hơn gold.')
    else:
        cv, y = p.node(X, y + 40, W, fn('Bước 7. compute_acc_by_diff(exec_results, diff_json_path)', '',
            C('exec_result') + ' đã sắp xếp, ' + C('dev.json'),
            'Chia kết quả theo ' + C("content['difficulty']") + ' (simple / moderate / challenging).<br>'
            + C('acc_nhóm = Σ res / số câu của nhóm;  all_acc = Σ res / 1534') + '; nhân 100',
            C('simple_acc, moderate_acc, challenging_acc, all_acc') + ' (%), ' + C('count_lists = [925, 464, 145, 1534]')), S_FN_EVAL)
        fm = ('<b>CÔNG THỨC EX</b><hr>EX = (1/N) · Σ<sub>n</sub> 𝟙(V̂<sub>n</sub> = V<sub>n</sub>) × 100<br>'
              'V̂ = tập kết quả của SQL dự đoán, V = tập kết quả của gold SQL, N = 1.534<br><hr>'
              '<b>Các trường hợp res = 0:</b><br>• kết quả khác gold<br>• SQL lỗi (no such column / function, syntax…)<br>'
              '• chạy quá ' + C('meta_time_out') + ' giây<br>• SQL rỗng ' + C('"SELECT"') + ' (do lỗi gọi model)<br><hr>'
              '<b>Ví dụ câu 1379:</b> pred ' + C("COUNT(*) … STRFTIME('%Y', event_date) = '2020'") + ' và gold ' +
              C("COUNT(event_id) … SUBSTR(event_date,1,4) = '2020'") + ' cùng trả [(n,)] → res = 1')
    p.edge(s, cv, '')
    pr, y = p.node(X, y + 40, W, fn(('Bước 8. ' if is_ves else 'Bước 7. ') + 'print_data(score_lists, count_lists)', '', '4 điểm + 4 số lượng',
        'In bảng ra console', '<br>' + C('&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;simple&nbsp;&nbsp;moderate&nbsp;&nbsp;challenging&nbsp;&nbsp;total<br>'
        'count&nbsp;&nbsp;&nbsp;925&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;464&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;145&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;1534<br>' +
        ('ves&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;…' if is_ves else 'accuracy&nbsp;…'))), S_FN_EVAL)
    p.edge(cv, pr, '')
    p.node(XR, 110, 560, fm, S_NOTE)
    p.node(XR, 520, 560, '<b>CHẠY 2 TRƯỜNG HỢP</b><hr>'
           '<b>' + ('VES' if is_ves else 'EX') + ' with knowledge:</b><br>' + C('--predicted_sql_path ./exp_result/openai_output/') + '<br>'
           '<b>' + ('VES' if is_ves else 'EX') + ' without knowledge:</b><br>' + C('--predicted_sql_path ./exp_result/openai_0_output/') + '<br><hr>'
           'Các model khác: ' + C('ollama_deepseekcoder_output/') + ' + ' + C('ollama_deepseekcoder_0_output/') + ', ' +
           C('ollama_gwen25_output/') + ' + ' + C('_0_output/') + ', ' + C('ollama_gemma3_output/') + ' + ' + C('_0_output/') + '<br>'
           'Gold, CSDL, dev.json giữ nguyên ở mọi lượt — chỉ đổi thư mục dự đoán.', S_NOTE)
    p.node(XR, 780, 560, '<b>MỞ RỘNG: chấm theo 6 mức SQL</b> — ' + C('app/scripts/ex_ves_by_category.py') + '<hr>'
           'Import lại ' + C('evaluation.package_sqls / execute_model') + ' và ' + C('evaluation_ves.execute_model / compute_ves') +
           '; ' + C('classify(gold)') + ' để chia câu vào mức 1–6; gọi thẳng ' + C('execute_model') +
           ' từng câu (tránh chia 0 của compute_acc_by_diff khi tập con thiếu một độ khó) → ' +
           C('ex_ves_by_category_&lt;db&gt;.csv / .xlsx'), S_NOTE)
    return p


eval_page('2b. Chấm EX (evaluation.py)', '③ CHẤM EX — Execution Accuracy (evaluation.py)', 'evaluation.py', False)
eval_page('2c. Chấm VES (evaluation_ves.py)', '③ CHẤM VES — Valid Efficiency Score (evaluation_ves.py)', 'evaluation_ves.py', True)

# =====================================================================================
# PAGE 2d — MA TRẬN CHẠY & BẢNG KẾT QUẢ
# =====================================================================================
p = Page('2d. Ma trận chạy & Bảng kết quả', 1900, 1500)
pages.append(p)
p.node(40, 20, 1800, '④ MA TRẬN CHẠY & BẢNG KẾT QUẢ CUỐI CÙNG', S_TITLE, 40)

loop, y = p.node(40, 90, 520, fn('Vòng ngoài: for model in MODELS', 'Kaggle notebook / terminal',
    'MODELS = [gpt-3.5-turbo, deepseek-coder-v2:16b, qwen2.5-coder:7b, gemma3:12b, (gpt-oss-20b/120b qua Groq…)]',
    'Với mỗi model chạy 2 cấu hình (with / without knowledge) qua luồng ② → mỗi cấu hình 1 file predict_dev.json', '8–10 file predict_dev.json'), S_FN)
w1, y1 = p.node(40, y + 50, 250, '<b>with knowledge</b><br>' + C('python src/ollama_request2.py --model qwen2.5-coder:7b --data_output_path exp_result/ollama_gwen25_output/predict_dev.json'), S_FN)
w0, y0 = p.node(310, y + 50, 250, '<b>without knowledge</b><br>' + C('python src/ollama_request2.py --model qwen2.5-coder:7b --no_knowledge --data_output_path exp_result/ollama_gwen25_0_output/predict_dev.json'), S_FN)
p.edge(loop, w1, '')
p.edge(loop, w0, '')
y = max(y1, y0)
ee, y = p.node(40, y + 50, 520, '<b>Chấm mỗi thư mục</b><br>' + C('evaluation.py') + ' → EX · ' + C('evaluation_ves.py --iterate_num 5') + ' → VES<br>'
               '(notebook ' + C('run-evaluation-kaggle.ipynb') + ', ' + C('evaluation-and-ves-local.ipynb') + ')', S_FN_EVAL)
p.edge(w1, ee, '')
p.edge(w0, ee, '')
agg, y = p.node(40, y + 50, 520, '<b>Tổng hợp</b> → ' + C('exp_result/summary_ex_ves.csv') +
                '<br>cột: Model, EX_wo_knowledge, EX_w_knowledge, VES_wo_knowledge, VES_w_knowledge', S_DATA)
p.edge(ee, agg, '4 số / model')

tbl = ('<b>BẢNG KẾT QUẢ (dev 1.534 câu)</b><hr>'
       '<table border="1" cellpadding="5" style="border-collapse:collapse;font-size:12px">'
       '<tr style="background:#eeeeee"><th>Model</th><th>EX w/o KG</th><th>EX w/ KG</th><th>VES w/o KG</th><th>VES w/ KG</th><th>Nguồn</th></tr>'
       '<tr><td>ChatGPT (paper BIRD, Table 2)</td><td>—</td><td>37.22 (bản dev sửa 09/2023: 42.24)</td><td>—</td><td>—</td><td>paper / leaderboard</td></tr>'
       '<tr><td><b>GPT-3.5-Turbo</b> (tái lập)</td><td>31.23</td><td>47.78</td><td>33.88</td><td>53.88</td><td>summary_ex_ves.csv</td></tr>'
       '<tr><td>DeepSeek-Coder-V2 (Ollama)</td><td>…</td><td>42.11</td><td>…</td><td>45.80</td><td>gap3 ctrl</td></tr>'
       '<tr><td>Qwen2.5-Coder (Ollama)</td><td>…</td><td>53.85</td><td>…</td><td>59.83</td><td>gap3 ctrl</td></tr>'
       '<tr><td>Gemma3 (Ollama)</td><td>…</td><td>48.70</td><td>…</td><td>54.86</td><td>gap3 ctrl</td></tr>'
       '<tr><td>gpt-oss (Groq) / Gemini…</td><td>…</td><td>…</td><td>…</td><td>…</td><td>chưa chạy đủ</td></tr>'
       '</table><br>'
       '<b>…</b> = điền sau khi chấm thư mục ' + C('*_0_output/') + ' tương ứng. '
       'Số "gap3 ctrl" là lượt w/ KG với evidence gốc, đã sửa prompt (PROJECT_LOG mục 8.1).<hr>'
       '<b>Nhận xét mong đợi:</b> w/ KG &gt; w/o KG rõ rệt (GPT-3.5: +16.55 EX, +20.00 VES) → evidence là yếu tố then chốt; '
       'model code mở 7B–16B chạy local đã ngang/vượt GPT-3.5.')
p.node(620, 90, 1180, tbl, S_NOTE)

# =====================================================================================
# PAGE 3 — TEXT-TO-SQL CLUBQUERY
# =====================================================================================
p = Page('3. Luồng Text-to-SQL (ClubQuery)', 2100, 4600)
pages.append(p)
p.node(40, 20, 2000, '⑤ LUỒNG TEXT-TO-SQL — ứng dụng ClubQuery (1 câu hỏi → SQL → chạy → trả lời → UI)', S_TITLE, 40)
p.node(40, 60, 2000, 'Code: ' + C('app/frontend/app.js') + ' → ' + C('app/backend/main.py') + ' → ' + C('service.py') + ' → ' +
       C('prompt.py, llm.py, guard.py, answer.py') + '. CSDL nghiệp vụ: ' + C('student_club.sqlite') + '; CSDL ứng dụng: ' +
       C('app/data/app.sqlite') + ' (user, model_config, dev_question, benchmark_run/item, glossary_term, query_log).', S_SUB, 30)
X, W, XR = 40, 820, 960

u0, y = p.node(X, 110, W, fn('Bước 1. Người dùng đặt câu hỏi trên UI', 'app/frontend/app.js',
    'Đăng nhập (token) · gõ câu hỏi HOẶC chọn câu mẫu BIRD dev (student_club, id 1312–1469) · chọn chế độ live/replay · chọn model hoặc lượt benchmark · '
    'tick "Dùng evidence" · tick "Áp dụng từ điển nghiệp vụ" · (tuỳ chọn) gõ evidence',
    'Bấm <b>Hỏi</b> → ' + C("fetch('POST /api/ask', {headers: {Authorization: token}, body: AskIn})"),
    C('AskIn = {question, mode: "live"|"replay", model_id, run_id, dev_question_id, use_evidence, evidence, use_glossary}')), S_FN_APP)

u1, y = p.node(X, y + 50, W, fn('Bước 2. current_user(authorization) → main.ask(body, user, conn)', 'app/backend/main.py (FastAPI)',
    'Header ' + C('Authorization') + ', ' + C('body: AskIn') + ', ' + C('conn = db()') + ' (kết nối app.sqlite)',
    C('current_user') + ': tra token → ' + C('user = {id, username, role ∈ member|board|admin}') + ' (sai → 401)<br>'
    + C('main.ask') + ': không có question lẫn dev_question_id → 422; gọi ' +
    C('service.ask(conn, user, question, mode, model_id, run_id, dev_question_id, use_evidence, evidence, use_glossary)') +
    '; ' + C('ValueError') + ' → 422',
    'dict ' + C('out') + ' từ service.ask → JSON'), S_FN_APP)
p.edge(u0, u1, 'HTTP POST /api/ask')

s1, y = p.node(X, y + 50, W, fn('Bước 3. service.ask — khởi tạo & đọc câu mẫu', 'app/backend/service.py',
    C('dev_question_id') + ' (có thể None)',
    C('started = time.monotonic()') + '; tạo ' + C("out = {status, sql, columns, rows, answer, error, is_correct, gold_sql, evidence_used, glossary_used, …}") + '<br>'
    'Nếu có câu dev: ' + C('SELECT * FROM dev_question WHERE id = ?') + ' → ' + C('dev_q') + ' {question, evidence, gold_sql}; ' +
    C("question = dev_q['question']"),
    C('question') + ', ' + C('dev_q')), S_FN_APP)
p.edge(u1, s1, '')

dm, y = p.node(X + 260, y + 50, 300, 'mode ?', S_DEC, 90)
p.edge(s1, dm, '')

rp, yr = p.node(X, y + 40, 260, fn('Bước 4a. PHÁT LẠI (replay)', '', C('run_id, dev_question_id'),
    C('SELECT b.predicted_sql, r.model_id FROM benchmark_item b JOIN benchmark_run r … WHERE run_id=? AND question_id=?') +
    '<br>Không gọi LLM — lấy đúng SQL đã sinh ở luồng benchmark ② (nạp qua per_db_ex.py → POST /api/benchmark/import)',
    C('sql')), S_FN_APP)
p.edge(dm, rp, 'replay', exit=('0', '0.5'), entry=('0.5', '0'))

LX = X + 300
LW = W - 300
l1, y = p.node(LX, y + 40, LW, fn('Bước 4b.1 Chọn model', '', C('model_id'),
    C('SELECT * FROM model_config WHERE id=? AND is_active=1') + ' (không có → ValueError)',
    C('model = {provider, model_tag, base_url, api_key_env}') + ' VD gpt-3.5-turbo / qwen2.5-coder:7b @ http://localhost:11434/v1'), S_FN_APP)
p.edge(dm, l1, 'live', exit=('1', '0.5'), entry=('0.5', '0'))
l2, y = p.node(LX, y + 40, LW, fn('Bước 4b.2 Ghép evidence', 'match_glossary + normalize_pseudo_sql',
    C('dev_q.evidence') + ', ' + C('use_evidence') + ', ' + C('evidence') + ' tự nhập, ' + C('use_glossary') + ', ' + C('question'),
    C('parts = []') + '<br>• có câu dev &amp; use_evidence → ' + C("parts.append(dev_q['evidence'])") +
    '<br>• else có evidence tự nhập → thêm vào<br>• use_glossary → ' + C('match_glossary(conn, question)') +
    ': lấy thuật ngữ đang bật có xuất hiện trong câu hỏi (lowercase) → thêm ' + C('"&lt;term&gt; refers to &lt;definition&gt;"') +
    '<br>• ' + C("knowledge = normalize_pseudo_sql('; '.join(parts))") + ' hoặc None<br>'
    '(tương đương WITH / WITHOUT knowledge của benchmark)',
    C('knowledge') + ' → lưu ' + C("out['evidence_used']") + ', ' + C("out['glossary_used']")), S_FN_APP)
p.edge(l1, l2, '')
l3, y = p.node(LX, y + 40, LW, fn('Bước 4b.3 Dựng prompt — prompt.build_prompt(question, knowledge, role)', 'app/backend/prompt.py',
    C('question') + ', ' + C('knowledge') + ', ' + C("user['role']"),
    C('schema_prompt(role)') + ': CREATE TABLE từ student_club.sqlite, <b>lọc bảng/cột theo vai trò</b> '
    '(member: bỏ budget, expense, income, member.email, member.phone); cache theo role<br>'
    + C('comment_prompt(question, knowledge)') + ': giống ' + C('generate_comment_prompt') + ' ở ②<br>'
    'Ghép: ' + C("schema + '\\n\\n' + comment + '\\nRespond with the final SQLite query only, inside a ```sql code block. …'"),
    C('prompt') + ' (giống prompt của ollama_request.py)'), S_FN)
p.edge(l2, l3, 'knowledge')
l4, y = p.node(LX, y + 40, LW, fn('Bước 4b.4 Gọi LLM + tách SQL — llm.generate_sql(model, prompt, timeout_s=120)', 'app/backend/llm.py',
    C('model') + ' (dict), ' + C('prompt'),
    C('llm.complete(model, prompt, max_tokens=512)') + ': ' + C('OpenAI(api_key=env[api_key_env], base_url=model.base_url)') +
    ' → ' + C("chat.completions.create(model=model_tag, messages=[{'role':'user','content':prompt}], temperature=0, max_tokens=512)") +
    ' (OpenAI / Groq / Ollama đều tương thích API OpenAI)<br>'
    + C('extract_sql(raw)') + ' — import từ ' + C('ollama_request.py') + ' (cùng hàm với benchmark)<br>'
    'Lỗi → ' + C('LLMError') + ' → ' + C("QueryRejected('FAILED_GENERATION')"),
    C('sql')), S_FN_LLM)
p.edge(l3, l4, 'prompt')

y = max(y, yr)
g1, y = p.node(X, y + 60, W, fn('Bước 5. guard.check_select(sql) — lớp chặn 1 (trên chuỗi)', 'app/backend/guard.py',
    C('sql') + ' (từ live hoặc replay); ' + C("out['sql'] = sql"),
    C('sqlparse.split(sql)') + ': rỗng → FAILED_GENERATION; &gt; 1 câu → REJECTED_UNSAFE<br>'
    'Từ khoá đầu ∈ {INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, PRAGMA, ATTACH…} → REJECTED_UNSAFE<br>'
    'Không bắt đầu bằng SELECT / WITH → FAILED_GENERATION',
    C('sql') + ' đã bỏ ; cuối'), S_FN_GUARD)
p.edge(l4, g1, 'sql', exit=('0.5', '1'), entry=('0.75', '0'))
p.edge(rp, g1, 'sql', exit=('0.5', '1'), entry=('0.15', '0'))
g2, y = p.node(X, y + 40, W, fn('Bước 6. guard.execute(sql, role, timeout_s=10) — lớp chặn 2 (trong SQLite)', 'app/backend/guard.py',
    C('sql') + ', ' + C('role'),
    C("connect_readonly()") + ': mở student_club.sqlite với ' + C('?mode=ro') + '<br>'
    + C('conn.set_authorizer(_authorizer(role, denied))') + ': chỉ cho SELECT/READ/FUNCTION/RECURSIVE; đọc bảng/cột bị cấm theo role → từ chối<br>'
    + C('conn.set_progress_handler(…)') + ': quá 10 s → ngắt<br>'
    + C('cursor.execute(sql); rows = fetchall()') + '; ' + C('columns = [d[0] for d in cursor.description]'),
    C('(columns, rows)') + ' → ' + C("out.status = 'EXECUTED'") + ', rows cắt tối đa ' + C('MAX_ROWS = 1000') + ' (truncated)'), S_FN_GUARD)
p.edge(g1, g2, 'sql an toàn')
an_, y = p.node(X, y + 40, W, fn('Bước 7. answer.make_answer(question, columns, rows, model)', 'app/backend/answer.py',
    C('question') + ', ' + C('columns') + ', ' + C('rows') + ', ' + C('model') + ' (None nếu replay)',
    'Live: ' + C('llm_answer') + ' gửi câu hỏi + tối đa 30 dòng đầu cho LLM, yêu cầu trả lời 1–3 câu tiếng Việt chỉ dựa trên dữ liệu<br>'
    'Replay / LLM lỗi: ' + C('template_answer(columns, rows)') + ' → "Kết quả: 12." / "Có 5 kết quả: …"',
    C('(answer, answer_source ∈ {llm, template})')), S_FN_LLM)
p.edge(g2, an_, 'columns, rows')
cg, y = p.node(X, y + 40, W, fn('Bước 8. So với đáp án gold (chỉ khi là câu dev — cả live và replay)', 'service.py',
    C("dev_q['gold_sql']") + ', ' + C('rows') + ' của SQL sinh ra',
    C("gold_cols, gold_rows = guard.execute(gold_sql, 'admin', timeout_s=30)") + '<br>'
    + C('same_result(rows, gold_rows) = set(rows) == set(gold_rows)') + ' — <b>cùng tiêu chí với execute_sql của evaluation.py</b> (EX)<br>'
    'Gold SQL không chạy được → ' + C('is_correct = None') + '. (Nếu SQL sinh ra bị chặn/lỗi ở bước 5/6: REJECTED_PERMISSION → None, lỗi khác → 0)',
    C("out['gold_sql']") + ', ' + C("out['is_correct'] ∈ {1, 0, None}")), S_FN_EVAL)
p.edge(an_, cg, '')
lg, y = p.node(X, y + 40, W, fn('Bước 9. Ghi query_log (finally — kể cả khi lỗi/bị chặn)', 'service.py → app.sqlite',
    'toàn bộ ' + C('out') + ', ' + C('user') + ', ' + C('latency_ms = (monotonic() - started)·1000'),
    C('INSERT INTO query_log (user_id, question, mode, model_id, run_id, evidence_used, glossary_used, sql, answer, status, error, latency_ms, row_count, is_correct, …)'),
    C("out['log_id']") + ', ' + C("out['latency_ms']")), S_FN_APP)
p.edge(cg, lg, '')
rr, y = p.node(X, y + 40, W, fn('Bước 10. Trả JSON → app.js renderResult(out)', 'app/frontend/app.js',
    'JSON: ' + C('status, sql, columns, rows, row_count, truncated, answer, answer_source, evidence_used, glossary_used, gold_sql, is_correct, error, latency_ms, log_id'),
    'Hiển thị: badge trạng thái · khối SQL · bảng kết quả (≤1000 dòng) · câu trả lời tiếng Việt (nguồn llm/template) · evidence đã đưa vào prompt · '
    'thuật ngữ đã áp dụng · gold SQL + nhãn <b>Đúng/Sai</b> · thời gian xử lý · nút feedback / xuất CSV (board, admin)',
    'Màn hình kết quả cho người dùng'), S_FN_APP)
p.edge(lg, rr, 'out (JSON)')

# lỗi
err, _ = p.node(XR, 110, 560, '<b>TRẠNG THÁI LỖI (QueryRejected → out.status)</b><hr>'
    '<table border="1" cellpadding="4" style="border-collapse:collapse;font-size:11px">'
    '<tr><th>status</th><th>Phát sinh ở</th><th>Khi nào</th></tr>'
    '<tr><td>FAILED_GENERATION</td><td>bước 4b.4, 5</td><td>LLM lỗi / SQL rỗng / không phải SELECT</td></tr>'
    '<tr><td>REJECTED_UNSAFE</td><td>bước 5, 6</td><td>nhiều câu, lệnh ghi/xoá/PRAGMA…</td></tr>'
    '<tr><td>REJECTED_PERMISSION</td><td>bước 6</td><td>đọc bảng/cột role không được xem</td></tr>'
    '<tr><td>TIMEOUT</td><td>bước 6</td><td>chạy &gt; 10 s</td></tr>'
    '<tr><td>EXEC_ERROR</td><td>bước 6</td><td>sai tên cột, sai cú pháp…</td></tr>'
    '<tr><td>EXECUTED</td><td>bước 6</td><td>thành công</td></tr></table><br>'
    'Có lỗi → bỏ qua bước 7, 8 (is_correct = 0 với câu dev, trừ REJECTED_PERMISSION = None), vẫn ghi log (bước 9) và trả về UI.', S_NOTE)
p.edge(g1, err, 'lỗi', S_EDGE_DASH, exit=('1', '0.3'), entry=('0', '0.6'))
p.edge(g2, err, 'lỗi', S_EDGE_DASH, exit=('1', '0.3'), entry=('0', '0.8'))

cmpb, _ = p.node(XR, 560, 560, '<b>SO SÁNH VỚI LUỒNG BENCHMARK ②</b><hr>'
    '<table border="1" cellpadding="4" style="border-collapse:collapse;font-size:11px">'
    '<tr><th></th><th>Benchmark ②</th><th>Text-to-SQL ⑤</th></tr>'
    '<tr><td>Đầu vào</td><td>1.534 câu dev.json (batch)</td><td>1 câu người dùng / câu dev</td></tr>'
    '<tr><td>Knowledge</td><td>evidence hoặc None (--no_knowledge)</td><td>evidence + từ điển nghiệp vụ, chuẩn hoá</td></tr>'
    '<tr><td>Schema</td><td>toàn bộ CREATE TABLE</td><td>lọc theo vai trò người dùng</td></tr>'
    '<tr><td>Gọi LLM</td><td>call_openai / call_ollama</td><td>llm.complete (OpenAI-compatible)</td></tr>'
    '<tr><td>Tách SQL</td><td colspan="2">extract_sql (dùng chung)</td></tr>'
    '<tr><td>Sau khi có SQL</td><td>ghép + ghi predict_dev.json</td><td>check_select → execute read-only → answer</td></tr>'
    '<tr><td>So đáp án</td><td>evaluation.py (EX), evaluation_ves.py (VES) cho cả tập</td><td>same_result từng câu (cùng tiêu chí EX)</td></tr>'
    '<tr><td>Đầu ra</td><td>điểm EX / VES</td><td>bảng kết quả + câu trả lời trên UI + query_log</td></tr>'
    '</table>', S_NOTE)

exs, _ = p.node(XR, 1080, 560, '<b>VÍ DỤ: câu 1379, live, vai trò thủ quỹ (board), tick evidence</b><hr>'
    'evidence_used = ' + C("meeting events refers to type = 'Meeting'; held in 2020 refers to CAST(STRFTIME('%Y', event_date) AS INTEGER) = 2020") + '<br>'
    'sql = ' + C("SELECT COUNT(*) FROM event WHERE type = 'Meeting' AND …") + '<br>'
    'status = EXECUTED, columns = [COUNT(*)], rows = [[n]]<br>'
    'answer = "Năm 2020 câu lạc bộ đã tổ chức n buổi họp."<br>'
    'gold chạy ra [[n]] → is_correct = 1 → UI hiện nhãn Đúng', S_NOTE)

# ---------------------------------------------------------------- write
xml = ('<mxfile host="app.diagrams.net" agent="claude" version="24.0.0">' +
       ''.join(pg.xml('p%d' % i) for i, pg in enumerate(pages)) + '</mxfile>')
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(xml)
print('ok', len(pages), 'pages', len(xml), 'bytes')
