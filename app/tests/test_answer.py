"""UC02f: câu trả lời dựng theo mẫu khi không dùng model."""
from app.backend.answer import template_answer


def test_empty():
    assert template_answer(['x'], []) == 'Không có dữ liệu phù hợp với câu hỏi.'


def test_single_value():
    assert template_answer(['COUNT(*)'], [(9,)]) == 'Kết quả: 9.'
    assert template_answer(['avg'], [(3.5,)]) == 'Kết quả: 3.5.'
    assert template_answer(['avg'], [(None,)]) == 'Kết quả: (trống).'


def test_single_row():
    assert template_answer(['first_name', 'last_name'], [('Angela', 'Sanders')]) == \
        'Kết quả: first_name = Angela; last_name = Sanders.'


def test_list():
    assert template_answer(['major_name'], [('Law',), ('Business',)]) == 'Có 2 kết quả: Law, Business.'
    rows = [(f'n{i}',) for i in range(12)]
    assert template_answer(['n'], rows).endswith('n9 và 2 kết quả khác.')


def test_table():
    assert template_answer(['a', 'b'], [(1, 2), (3, 4)]) == 'Có 2 dòng kết quả, xem bảng bên dưới.'
