#!/usr/bin/env python3
"""
Dựng BAO_CAO.docx từ BAO_CAO.md (pandoc + python-docx).

  venv/Scripts/python -m pip install pypandoc_binary python-docx
  venv/Scripts/python docs/pttk/build_docx.py
"""
import os
import re
import tempfile

import pypandoc
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
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
Hệ thống hỏi đáp dữ liệu câu lạc bộ sinh viên bằng ngôn ngữ tự nhiên: nghiên cứu bài báo BIRD và ứng dụng
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
    body = body.replace('(screens/06_mobile.png)', '(screens/06_mobile.png){width=6cm}')
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
    data = pypandoc.convert_text('', 'docx', format='md', outputfile=path, extra_args=[])
    del data
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


def set_cell_shading(cell, hex_fill):
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_fill)
    tcpr.append(shd)


def post_process(path: str):
    doc = Document(path)
    for table in doc.tables:
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        tblpr = table._tbl.tblPr
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
        for r_i, row in enumerate(table.rows):
            for cell in row.cells:
                if r_i == 0:
                    set_cell_shading(cell, 'E7EEF7')
                for p in cell.paragraphs:
                    p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    p.paragraph_format.line_spacing = 1.1
                    p.paragraph_format.space_after = Pt(2)
                    for run in p.runs:
                        run.font.size = Pt(11)
                        if r_i == 0:
                            run.font.bold = True
    # ảnh căn giữa
    for p in doc.paragraphs:
        if p._p.xpath('.//w:drawing'):
            p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    # Word hỏi cập nhật mục lục khi mở
    settings = doc.settings.element
    upd = OxmlElement('w:updateFields')
    upd.set(qn('w:val'), 'true')
    settings.append(upd)
    # số trang ở chân trang
    footer = doc.sections[0].footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for kind, text in (('begin', None), (None, 'PAGE'), ('end', None)):
        run = footer.add_run()
        if kind:
            fc = OxmlElement('w:fldChar')
            fc.set(qn('w:fldCharType'), kind)
            run._r.append(fc)
        else:
            it = OxmlElement('w:instrText')
            it.set(qn('xml:space'), 'preserve')
            it.text = text
            run._r.append(it)
    doc.save(path)


def main():
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
    main()
