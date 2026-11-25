"""UC02f: câu trả lời dựng theo mẫu khi không dùng model."""
from app.backend.answer import template_answer


def test_empty():
    assert template_answer(['x'], []) == 'No matching data was found.'


def test_single_value():
    assert template_answer(['COUNT(*)'], [(9,)]) == 'Result: 9.'
    assert template_answer(['avg'], [(3.5,)]) == 'Result: 3.5.'
    assert template_answer(['avg'], [(None,)]) == 'Result: (empty).'


def test_single_row():
    assert template_answer(['first_name', 'last_name'], [('Angela', 'Sanders')]) == \
        'Result: first_name = Angela; last_name = Sanders.'


def test_list():
    assert template_answer(['major_name'], [('Law',), ('Business',)]) == '2 results: Law, Business.'
    rows = [(f'n{i}',) for i in range(12)]
    assert template_answer(['n'], rows).endswith('n9 and 2 more.')


def test_table():
    assert template_answer(['a', 'b'], [(1, 2), (3, 4)]) == '2 rows returned — see the table below.'
