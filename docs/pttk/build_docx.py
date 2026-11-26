#!/usr/bin/env python3
"""
Dựng báo cáo Word.

  venv/Scripts/python -m pip install python-docx           (thêm pypandoc_binary nếu dựng BAO_CAO.docx)
  venv/Scripts/python docs/pttk/build_docx.py              -> PTKTHTTT_NC_Nhom5_capnhat.docx (báo cáo nhóm)
  venv/Scripts/python docs/pttk/build_docx.py --bao-cao    -> BAO_CAO.docx (bản rút gọn từ BAO_CAO.md)

Báo cáo nhóm dùng chính file Word gốc PTKTHTTT_NC_Nhom5.docx làm khuôn: giữ bìa, lời cảm ơn, bảng phân
công, danh mục, style (Heading 1–3, "Chu thich bang", "Chu thich hinh", List Paragraph) và nguyên
Chương II (có hình công thức); các chương khác được sinh lại từ BAO_CAO_NHOM5.md theo đúng định dạng của
file gốc (bảng viền đơn, hàng tiêu đề nền D9D9D9, chữ 12pt; khối mã nền F2F2F2, Courier New 10pt).
Mục lục, danh mục bảng/hình là trường (field) của Word: mở file và chọn Có khi Word hỏi cập nhật trường
(hoặc Ctrl+A, F9).
"""
import os
import re
import sys
import tempfile
from xml.sax.saxutils import escape

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Emu, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))

# ======================================================================================
# Báo cáo nhóm (mặc định)
# ======================================================================================
TEMPLATE = os.path.join(HERE, 'PTKTHTTT_NC_Nhom5.docx')
GROUP_SRC = os.path.join(HERE, 'BAO_CAO_NHOM5.md')
GROUP_OUT = os.path.join(HERE, 'PTKTHTTT_NC_Nhom5_capnhat.docx')

W = nsdecls('w')
TABLE_WIDTH = 9071            # dxa, như bảng trong file gốc (A4, lề trái 3 cm, phải 2 cm)
MAX_IMG_W = Cm(16)
MAX_IMG_H = Cm(21)
BULLET_NUM = 3                # numId gạch đầu dòng (●, cấp 2 là -) trong numbering.xml của file gốc
DECIMAL_ABSTRACT = 1          # abstractNum đánh số 1. 2. 3.

# Sửa nhỏ ở phần giữ nguyên của file gốc: (đoạn cũ, đoạn mới)
FRONT_EDITS = [
    ('CLUBQUERY – HỆ THỐNG HỎI ĐÁP DỮ LIỆU CÂU LẠC BỘ SINH VIÊN', 'CLUBQUERY – HỆ THỐNG QUẢN LÝ CÂU LẠC BỘ SINH VIÊN'),
    ('BẰNG NGÔN NGỮ TỰ NHIÊN:', 'CÓ HỎI ĐÁP DỮ LIỆU BẰNG NGÔN NGỮ TỰ NHIÊN:'),
    ('Nhóm thực hiện: Nhóm 4', 'Nhóm thực hiện: Nhóm 5'),
]
CHAPTER2_EDITS = [
    ('ClubQuery hiện thực hoá ý đó bằng từ điển nghiệp vụ.',
     'ClubQuery hiện thực hoá ý đó bằng từ điển nghiệp vụ và ô tri thức ngoài khi hỏi đáp.'),
    ('ClubQuery dùng lại hàm này cho evidence và cho từ điển nghiệp vụ.',
     'ClubQuery dùng lại hàm này cho định nghĩa trong từ điển nghiệp vụ; evidence của câu hỏi mẫu BIRD '
     'được giữ nguyên văn như lúc benchmark (mục 6.3.1).'),
]


def x(s):
    return escape(s, {'"': '&quot;'})


# ---------- run và đoạn ----------
INLINE = re.compile(r'(\*\*[^*]+\*\*|`[^`]+`|(?<![\w*])\*[^*\s][^*]*?\*(?![\w*]))')


def run(text, bold=False, italic=False, code=False, size=None, code_size=24):
    rpr = ''
    if code:
        rpr += '<w:rFonts w:ascii="Courier New" w:eastAsia="Courier New" w:hAnsi="Courier New" w:cs="Courier New"/>'
    if bold:
        rpr += '<w:b/><w:bCs/>'
    if italic:
        rpr += '<w:i/><w:iCs/>'
    sz = code_size if code and size is None else size
    if sz:
        rpr += f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>'
    return f'<w:r>{"<w:rPr>" + rpr + "</w:rPr>" if rpr else ""}<w:t xml:space="preserve">{x(text)}</w:t></w:r>'


def runs(text, size=None, bold=False):
    out = []
    for tok in INLINE.split(text):
        if not tok:
            continue
        if tok.startswith('**') and tok.endswith('**'):
            out.append(run(tok[2:-2], bold=True, size=size))
        elif tok.startswith('`') and tok.endswith('`'):
            out.append(run(tok[1:-1], code=True, size=size, bold=bold))
        elif tok.startswith('*') and tok.endswith('*') and len(tok) > 2:
            out.append(run(tok[1:-1], italic=True, size=size, bold=bold))
        else:
            out.append(run(tok, size=size, bold=bold))
    return ''.join(out)


def p_xml(ppr, content):
    return parse_xml(f'<w:p {W}><w:pPr>{ppr}</w:pPr>{content}</w:p>')


def heading(level, text):
    return p_xml(f'<w:pStyle w:val="Heading{level}"/>', run(text))


def paragraph(text):
    keep = '<w:keepNext/>' if text.rstrip().endswith(':') else ''  # câu dẫn đi cùng khối mã/danh sách sau nó
    return p_xml(f'{keep}<w:spacing w:after="120"/><w:jc w:val="both"/>', runs(text))


def list_item(text, num_id, level=0):
    return p_xml(f'<w:pStyle w:val="ListParagraph"/><w:numPr><w:ilvl w:val="{level}"/><w:numId w:val="{num_id}"/>'
                 '</w:numPr><w:spacing w:after="80"/><w:jc w:val="both"/>', runs(text))


def caption(kind, text):
    return p_xml(f'<w:pStyle w:val="{kind}"/>', run(text))


def code_lines(lines):
    out = []
    for i, line in enumerate(lines):
        last = i == len(lines) - 1
        ppr = ('' if last else '<w:keepNext/>') + '<w:keepLines/><w:shd w:val="clear" w:color="auto" w:fill="F2F2F2"/>' \
              f'<w:spacing w:before="{60 if i == 0 else 0}" w:after="{120 if last else 0}" w:line="240" w:lineRule="auto"/>' \
              '<w:ind w:left="200" w:right="200"/>'
        out.append(p_xml(ppr, run(line, code=True, size=16) if line else ''))
    return out


# ---------- bảng ----------
CELL_BORDERS = ''.join(f'<w:{e} w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
                       for e in ('top', 'left', 'bottom', 'right'))
TBL_BORDERS = ''.join(f'<w:{e} w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
                      for e in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'))


def plain(s):
    return re.sub(r'[`*]', '', s)


def col_widths(rows, n):
    if n == 2 and rows[0][0].strip() == 'Use Case ID':
        return [2358, TABLE_WIDTH - 2358]
    weights, mins = [], []
    for c in range(n):
        longest = max(max((len(plain(part)) for part in r[c].split('<br>')), default=0) for r in rows)
        weights.append(min(max(longest, 5), 60) ** 0.8)
        # cột phải chứa được từ dài nhất (mã, tên quyền) mà không ngắt giữa chữ
        word = 0
        for i, r in enumerate(rows):
            for tok in re.findall(r'`[^`]+`|\S+', r[c].replace('<br>', ' ')):
                code = tok.startswith('`')
                k = 1.15 if i == 0 else 1.0                       # hàng tiêu đề in đậm
                word = max(word, len(plain(tok)) * (150 if code else 170) * k)
        mins.append(min(int(word) + 260, 2600))                   # mã rất dài thì cho xuống dòng
    if sum(mins) > TABLE_WIDTH * 0.9:
        mins = [int(m * TABLE_WIDTH * 0.9 / sum(mins)) for m in mins]
    widths = [max(m, int(TABLE_WIDTH * w / sum(weights))) for m, w in zip(mins, weights)]
    over = sum(widths) - TABLE_WIDTH
    if over > 0:                                                  # lấy bớt từ các cột rộng hơn mức tối thiểu
        slack = [w - m for w, m in zip(widths, mins)]
        total_slack = sum(slack) or 1
        widths = [w - int(over * s / total_slack) for w, s in zip(widths, slack)]
    widths[-1] += TABLE_WIDTH - sum(widths)
    return widths


def cell(text, width, header, center, shade):
    ppr = '<w:keepNext/>' if header else ''
    ppr += '<w:spacing w:before="30" w:after="30" w:line="264" w:lineRule="auto"/>'
    if center:
        ppr += '<w:jc w:val="center"/>'
    paras = ''.join(f'<w:p><w:pPr>{ppr}</w:pPr>{runs(part.strip(), size=24, bold=header)}</w:p>'
                    for part in (text.split('<br>') if text else ['']))
    tcpr = f'<w:tcW w:w="{width}" w:type="dxa"/><w:tcBorders>{CELL_BORDERS}</w:tcBorders>'
    if shade:
        tcpr += '<w:shd w:val="clear" w:color="auto" w:fill="D9D9D9"/>'
    tcpr += ('<w:tcMar><w:top w:w="60" w:type="dxa"/><w:left w:w="100" w:type="dxa"/>'
             '<w:bottom w:w="60" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tcMar><w:vAlign w:val="center"/>')
    return f'<w:tc><w:tcPr>{tcpr}</w:tcPr>{paras}</w:tc>'


def table(rows):
    n = max(len(r) for r in rows)
    rows = [r + [''] * (n - len(r)) for r in rows]
    widths = col_widths(rows, n)
    use_case = rows[0][0].strip() == 'Use Case ID'
    body = rows[1:]
    center = [bool(body) and max(len(plain(r[c])) for r in body) <= 8 for c in range(n)]
    xml = [f'<w:tbl {W}><w:tblPr><w:tblW w:w="{TABLE_WIDTH}" w:type="dxa"/><w:jc w:val="center"/>'
           f'<w:tblBorders>{TBL_BORDERS}</w:tblBorders><w:tblLayout w:type="fixed"/>'
           '<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" w:firstColumn="1" w:lastColumn="0" '
           'w:noHBand="0" w:noVBand="1"/></w:tblPr><w:tblGrid>'
           + ''.join(f'<w:gridCol w:w="{w}"/>' for w in widths) + '</w:tblGrid>']
    for i, r in enumerate(rows):
        header = i == 0
        trpr = '<w:cantSplit/>' + ('<w:tblHeader/>' if header and not use_case else '')
        xml.append(f'<w:tr><w:trPr>{trpr}</w:trPr>' + ''.join(
            cell(r[c], widths[c], header, header or center[c], header and not use_case) for c in range(n)) + '</w:tr>')
    xml.append('</w:tbl>')
    return parse_xml(''.join(xml))


def split_row(line):
    line = line.strip()
    if line.startswith('|'):
        line = line[1:]
    if line.endswith('|'):
        line = line[:-1]
    return [c.strip() for c in line.split('|')]


# ---------- hình ----------
def picture(doc, path, width_cm=None):
    part = doc.part
    _, image = part.get_or_add_image(path)
    ratio = image.px_height / image.px_width
    width = Cm(width_cm) if width_cm else min(MAX_IMG_W, Emu(int(image.px_width * 914400 / 96)))
    height = int(width * ratio)
    if height > MAX_IMG_H:
        height = MAX_IMG_H
        width = int(height / ratio)
    inline = part.new_pic_inline(path, Emu(int(width)), Emu(int(height)))
    p = p_xml('<w:keepNext/><w:spacing w:before="60" w:after="120" w:line="240" w:lineRule="auto"/><w:jc w:val="center"/>',
              '<w:r><w:rPr><w:noProof/></w:rPr><w:drawing/></w:r>')
    p.find(f'.//{qn("w:drawing")}').append(inline)
    return p


# ---------- Markdown → phần tử Word ----------
CAPTION_TABLE = re.compile(r'^Bảng (\d+|PL)\.\d+\. ')
FIGURE = re.compile(r'^!\[(.+?)\]\((.+?)\)(?:\{width=([\d.]+)\})?$')
LIST = re.compile(r'^(\s*)([-*]|\d+\.) (.*)$')


class Builder:
    def __init__(self, doc):
        self.doc = doc
        numbering = doc.part.numbering_part.element
        self.numbering = numbering
        self.next_num = max(int(n.get(qn('w:numId'))) for n in numbering.findall(qn('w:num'))) + 1

    def new_decimal_list(self):
        num_id = self.next_num
        self.next_num += 1
        self.numbering.append(parse_xml(
            f'<w:num {W} w:numId="{num_id}"><w:abstractNumId w:val="{DECIMAL_ABSTRACT}"/>'
            '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride></w:num>'))
        return num_id

    def convert(self, md, chapter2):
        md = re.sub(r'<!--.*?-->', '', md, flags=re.S)
        lines = md.split('\n')
        out, i = [], 0
        while i < len(lines):
            line = lines[i]
            s = line.strip()
            if not s:
                i += 1
            elif s.startswith('```'):
                j = i + 1
                while not lines[j].strip().startswith('```'):
                    j += 1
                out += code_lines(lines[i + 1:j])
                i = j + 1
            elif s == '{{CHUONG_II}}':
                out += chapter2
                i += 1
            elif s.startswith('#'):
                level = len(s) - len(s.lstrip('#'))
                out.append(heading(level, s[level:].strip()))
                i += 1
            elif FIGURE.match(s):
                alt, path, width = FIGURE.match(s).groups()
                out.append(picture(self.doc, os.path.join(HERE, path), float(width) if width else None))
                out.append(caption('Chuthichhinh', alt))
                i += 1
            elif s.startswith('|'):
                rows = []
                while i < len(lines) and lines[i].strip().startswith('|'):
                    if not re.match(r'^\|?\s*:?-{3,}', lines[i].strip()):
                        rows.append(split_row(lines[i]))
                    i += 1
                out.append(table(rows))
                out.append(p_xml('<w:spacing w:after="60"/>', ''))
            elif CAPTION_TABLE.match(s):
                out.append(caption('Chuthichbang', s))
                i += 1
            elif LIST.match(line):
                num_id = None
                while i < len(lines) and LIST.match(lines[i]):
                    indent, marker, text = LIST.match(lines[i]).groups()
                    if marker[0].isdigit():
                        num_id = num_id if num_id and num_id != BULLET_NUM else self.new_decimal_list()
                        out.append(list_item(text, num_id))
                    else:
                        out.append(list_item(text, BULLET_NUM, 1 if len(indent) >= 2 else 0))
                    i += 1
            else:
                buf = []
                while i < len(lines) and lines[i].strip() and not re.match(r'^(#|\||```|!\[|\{\{)', lines[i].strip()) \
                        and not LIST.match(lines[i]):
                    buf.append(lines[i].strip())
                    i += 1
                out.append(paragraph(' '.join(buf)))
        return out


# ---------- thao tác trên file gốc ----------
def ptext(el):
    return ''.join(t.text or '' for t in el.iter(qn('w:t')))


def pstyle(el):
    ps = el.find(f'{qn("w:pPr")}/{qn("w:pStyle")}')
    return ps.get(qn('w:val')) if ps is not None else None


def replace_text(el, old, new):
    """Thay một câu trong đoạn; giữ định dạng của run chứa câu đó."""
    ts = list(el.iter(qn('w:t')))
    for t in ts:
        if t.text and old in t.text:
            t.text = t.text.replace(old, new)
            return True
    full = ''.join(t.text or '' for t in ts)
    if old not in full:
        return False
    ts[0].text = full.replace(old, new)
    ts[0].set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    for t in ts[1:]:
        t.text = ''
    return True


def reset_toc_fields(body):
    """Bỏ kết quả cũ của 3 trường TOC (mục lục, danh mục bảng, danh mục hình); Word dựng lại khi mở."""
    paras = list(body.iter(qn('w:p')))
    i = 0
    while i < len(paras):
        p = paras[i]
        instr = ''.join(t.text or '' for t in p.iter(qn('w:instrText')))
        if ' TOC ' not in instr:
            i += 1
            continue
        code = re.search(r' TOC [^<]*', instr).group(0)
        depth, j = 0, i
        while True:
            for fc in paras[j].iter(qn('w:fldChar')):
                t = fc.get(qn('w:fldCharType'))
                depth += t == 'begin'
                depth -= t == 'end'
            if depth <= 0:
                break
            j += 1
        new = parse_xml(
            f'<w:p {W}><w:pPr><w:pStyle w:val="TOC1"/></w:pPr>'
            '<w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>'
            f'<w:r><w:instrText xml:space="preserve">{x(code)}</w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            '<w:r><w:t>Nhấn chuột phải, chọn Update Field (hoặc Ctrl+A rồi F9) để cập nhật.</w:t></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')
        paras[i].addprevious(new)
        for k in range(i, j + 1):
            paras[k].getparent().remove(paras[k])
        i = j + 1


def build_group_report():
    doc = Document(TEMPLATE)
    body = doc.element.body
    children = list(body)
    sect = children[-1]

    def h1(prefix):
        for k, el in enumerate(children):
            if el.tag == qn('w:p') and pstyle(el) == 'Heading1' and ptext(el).startswith(prefix):
                return k
        raise SystemExit(f'Không thấy Heading 1 "{prefix}" trong {TEMPLATE}')

    start, ch2, ch3 = h1('CHƯƠNG I.'), h1('CHƯƠNG II.'), h1('CHƯƠNG III.')
    chapter2 = children[ch2:ch3]
    for old, new in CHAPTER2_EDITS:
        if not any(replace_text(el, old, new) for el in chapter2 if el.tag == qn('w:p')):
            print(f'! Chương II: không thấy "{old}"')
    for el in children[start:-1]:
        body.remove(el)

    for el in children[:start]:
        if el.tag == qn('w:p'):
            for old, new in FRONT_EDITS:
                if ptext(el).strip() == old:
                    replace_text(el, old, new)
    reset_toc_fields(body)

    md = open(GROUP_SRC, encoding='utf-8').read()
    for el in Builder(doc).convert(md, chapter2):
        sect.addprevious(el)

    # bỏ ảnh của các chương cũ không còn dùng
    used = set(re.findall(r'r:(?:embed|id)="(rId\d+)"', doc.element.xml))
    for rid, rel in list(doc.part.rels.items()):
        if rel.reltype.endswith('/image') and rid not in used:
            doc.part.drop_rel(rid)

    doc.save(GROUP_OUT)
    if update_fields_with_word(GROUP_OUT):
        print('   mục lục, danh mục bảng/hình đã cập nhật bằng Word')
    else:  # không có Word: để Word tự hỏi cập nhật trường khi mở file
        doc = Document(GROUP_OUT)
        upd = OxmlElement('w:updateFields')
        upd.set(qn('w:val'), 'true')
        doc.settings.element.append(upd)
        doc.save(GROUP_OUT)
        print('   mở bằng Word và chọn Có khi được hỏi cập nhật trường')
    print(f'-> {GROUP_OUT}')


def update_fields_with_word(path):
    """Windows có Microsoft Word: cập nhật mục lục và các trường qua COM (PowerShell)."""
    if os.name != 'nt':
        return False
    import subprocess
    ps = ("$ErrorActionPreference='Stop'; $w = New-Object -ComObject Word.Application; $w.Visible = $false; "
          "$w.DisplayAlerts = 0; try { $d = $w.Documents.Open($env:DOCX_PATH, $false, $false); "
          "$d.Fields.Update() | Out-Null; foreach ($t in $d.TablesOfContents) { $t.Update() }; "
          "$d.Save(); $d.Close($false) } finally { $w.Quit() }")
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-Command', ps], env={**os.environ, 'DOCX_PATH': path},
                           capture_output=True, timeout=600)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


# ======================================================================================
# BAO_CAO.docx (bản rút gọn, dựng bằng pandoc)
# ======================================================================================
SRC = os.path.join(HERE, 'BAO_CAO.md')
OUT = os.path.join(HERE, 'BAO_CAO.docx')
FONT = 'Times New Roman'

COVER = '''
::: {custom-style="Cover Info"}
[TÊN TRƯỜNG]

[TÊN KHOA]
:::

::: {custom-style="Cover Kind"}
BÁO CÁO ĐỒ ÁN MÔN PHÂN TÍCH THIẾT KẾ HỆ THỐNG THÔNG TIN
:::

::: {custom-style="Cover Title"}
CLUBQUERY
:::

::: {custom-style="Cover Subtitle"}
Hệ thống quản lý câu lạc bộ sinh viên có hỏi đáp dữ liệu bằng ngôn ngữ tự nhiên: nghiên cứu bài báo BIRD và ứng dụng
:::

::: {custom-style="Cover Info"}
Hướng đồ án: Nghiên cứu bài báo và phát triển hệ thống minh họa

Giảng viên hướng dẫn: [Họ tên giảng viên]

Sinh viên thực hiện: [Họ tên] — [MSSV]

Lớp: [Lớp]

Tháng 10/2026
:::

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

::: {custom-style="TOC Heading"}
MỤC LỤC
:::

```{=openxml}
<w:p><w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r><w:r><w:instrText xml:space="preserve"> TOC \\o "1-2" \\h \\z \\u </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>Mở bằng Word, chọn Có khi được hỏi cập nhật trường để hiện mục lục.</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>
```
'''


def prepare_markdown() -> str:
    md = open(SRC, encoding='utf-8').read()
    # bỏ bìa và mục lục dạng Markdown (từ đầu tới hết mục lục), thay bằng bìa + mục lục của Word
    body = md[md.index('## 1. Giới thiệu'):]
    body = re.sub(r'\n---\n', '\n', body)  # đường kẻ ngang giữa chương; Heading 1 đã tự sang trang
    body = body.replace('(screens/09_mobile.png)', '(screens/09_mobile.png){width=6cm}')
    return COVER + '\n' + separate_lists(body)


LIST_ITEM = re.compile(r'^\s*(\d+\.|[-*])\s')


def separate_lists(md: str) -> str:
    """Pandoc cần một dòng trống trước danh sách nằm ngay sau một đoạn văn."""
    out, in_code, prev = [], False, ''
    for line in md.split('\n'):
        if line.startswith('```'):
            in_code = not in_code
        if (not in_code and LIST_ITEM.match(line) and prev.strip()
                and not LIST_ITEM.match(prev) and not prev.startswith(('|', '  ', '```'))):
            out.append('')
        out.append(line)
        prev = line
    return '\n'.join(out)


def style_font(style, size=None, bold=None, color=None):
    style.font.name = FONT
    style.element.get_or_add_rPr()
    rfonts = style.element.rPr.find(qn('w:rFonts'))
    if rfonts is None:
        rfonts = OxmlElement('w:rFonts')
        style.element.rPr.append(rfonts)
    for a in ('w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia'):
        rfonts.set(qn(a), FONT)
    for a in ('w:asciiTheme', 'w:hAnsiTheme', 'w:eastAsiaTheme', 'w:cstheme'):
        rfonts.attrib.pop(qn(a), None)  # font theo theme sẽ đè lên font đã đặt
    if size:
        style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold
    if color is not None:
        style.font.color.rgb = color


def make_reference(path: str):
    import pypandoc
    pypandoc.convert_text('', 'docx', format='md', outputfile=path, extra_args=[])
    doc = Document(path)
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin, sec.right_margin = Cm(3), Cm(2)
    sec.top_margin, sec.bottom_margin = Cm(2), Cm(2)
    black = RGBColor(0, 0, 0)
    for name in ('Normal', 'Body Text', 'First Paragraph', 'Compact'):
        if name in [s.name for s in doc.styles]:
            st = doc.styles[name]
            style_font(st, 13)
            st.paragraph_format.line_spacing = 1.3
            st.paragraph_format.space_after = Pt(6)
            if name != 'Compact':
                st.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for name, size in (('Heading 1', 16), ('Heading 2', 14), ('Heading 3', 13), ('Title', 18)):
        st = doc.styles[name]
        style_font(st, size, True, black)
        st.font.italic = False
        st.paragraph_format.space_before = Pt(12)
        st.paragraph_format.space_after = Pt(6)
        st.paragraph_format.keep_with_next = True
    doc.styles['Heading 1'].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.styles['Heading 1'].paragraph_format.page_break_before = True  # mỗi chương sang trang mới
    doc.styles['Heading 1'].paragraph_format.space_before = Pt(0)
    for name in ('Image Caption', 'Captioned Figure'):
        if name in [s.name for s in doc.styles]:
            style_font(doc.styles[name], 12, False, black)
            doc.styles[name].font.italic = True
            doc.styles[name].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if 'Source Code' in [s.name for s in doc.styles]:
        code = doc.styles['Source Code'].paragraph_format
        code.alignment = WD_ALIGN_PARAGRAPH.LEFT  # không kế thừa căn đều của Normal
        code.line_spacing = 1.0
        code.space_after = Pt(0)
        doc.styles['Source Code'].font.size = Pt(9)

    from docx.enum.style import WD_STYLE_TYPE
    covers = {'Cover Info': (14, False), 'Cover Kind': (16, True), 'Cover Title': (28, True),
              'Cover Subtitle': (16, True), 'TOC Heading': (16, True)}
    names = {s.name for s in doc.styles}
    for name, (size, bold) in covers.items():
        st = doc.styles[name] if name in names else doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        st.base_style = doc.styles['Normal']
        style_font(st, size, bold, black)
        st.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        st.paragraph_format.space_after = Pt(6)
    doc.styles['Cover Kind'].paragraph_format.space_before = Pt(120)
    doc.styles['Cover Title'].paragraph_format.space_before = Pt(36)
    doc.styles['Cover Subtitle'].paragraph_format.space_after = Pt(100)
    doc.save(path)


def set_cell_shading(cell_, hex_fill):
    tcpr = cell_._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_fill)
    tcpr.append(shd)


def post_process(path: str):
    doc = Document(path)
    for tbl in doc.tables:
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tblpr = tbl._tbl.tblPr
        borders = OxmlElement('w:tblBorders')
        for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
            el = OxmlElement(f'w:{edge}')
            el.set(qn('w:val'), 'single')
            el.set(qn('w:sz'), '4')
            el.set(qn('w:color'), '808080')
            borders.append(el)
        old = tblpr.find(qn('w:tblBorders'))
        if old is not None:
            tblpr.remove(old)
        tblpr.append(borders)
        for r_i, row in enumerate(tbl.rows):
            for c in row.cells:
                if r_i == 0:
                    set_cell_shading(c, 'E7EEF7')
                for p in c.paragraphs:
                    p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    p.paragraph_format.line_spacing = 1.1
                    p.paragraph_format.space_after = Pt(2)
                    for r in p.runs:
                        r.font.size = Pt(11)
                        if r_i == 0:
                            r.font.bold = True
    for p in doc.paragraphs:  # ảnh căn giữa
        if p._p.xpath('.//w:drawing'):
            p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    settings = doc.settings.element  # Word hỏi cập nhật mục lục khi mở
    upd = OxmlElement('w:updateFields')
    upd.set(qn('w:val'), 'true')
    settings.append(upd)
    footer = doc.sections[0].footer.paragraphs[0]  # số trang ở chân trang
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for kind, text in (('begin', None), (None, 'PAGE'), ('end', None)):
        r = footer.add_run()
        if kind:
            fc = OxmlElement('w:fldChar')
            fc.set(qn('w:fldCharType'), kind)
            r._r.append(fc)
        else:
            it = OxmlElement('w:instrText')
            it.set(qn('xml:space'), 'preserve')
            it.text = text
            r._r.append(it)
    doc.save(path)


def build_bao_cao():
    import pypandoc
    with tempfile.TemporaryDirectory() as tmp:
        ref = os.path.join(tmp, 'reference.docx')
        make_reference(ref)
        pypandoc.convert_text(
            prepare_markdown(), 'docx', format='markdown+tex_math_dollars', outputfile=OUT,
            extra_args=['--shift-heading-level-by=-1', f'--reference-doc={ref}',
                        f'--resource-path={HERE}', '--metadata=lang:vi-VN'])
    post_process(OUT)
    print(f'-> {OUT}')


if __name__ == '__main__':
    if '--bao-cao' in sys.argv:
        build_bao_cao()
    else:
        build_group_report()
