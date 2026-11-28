"""Kiểm thử luồng hỏi đáp Text-to-SQL qua API. Không gọi model thật: llm.call_llm được giả lập."""
import pytest
from fastapi.testclient import TestClient

from app.backend import config, llm, prompt
from app.backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    """Không bao giờ gọi model thật trong test; ca nào cần thì tự giả lập."""
    def offline(*a, **k):
        raise llm.LLMError('test: không gọi model thật')
    monkeypatch.setattr(llm, 'call_llm', offline)


def fake_llm(sql_reply, answer_reply='ok'):
    """Giả lập LLM: lần gọi đầu (sinh SQL) trả sql_reply, lần sau (diễn giải) trả answer_reply."""
    calls = []

    def call(model, prompt_text, **kw):
        calls.append((prompt_text, kw))
        return sql_reply if len(calls) == 1 else answer_reply
    call.calls = calls
    return call


def model_id(name='Qwen2.5-Coder'):
    return next(m['id'] for m in client.get('/api/models').json() if m['name'] == name)


def ask(**body):
    return client.post('/api/ask', json={'model_id': model_id(), **body}).json()


def test_free_text_question(monkeypatch):
    llm_fake = fake_llm("```sql\nSELECT COUNT(*) FROM event WHERE type = 'Meeting'\n```",
                        'Câu lạc bộ đã tổ chức 18 buổi họp.')
    monkeypatch.setattr(llm, 'call_llm', llm_fake)
    r = ask(question='How many meeting events are there?')
    assert r['status'] == 'EXECUTED' and r['rows'][0][0] > 0
    assert r['sql'] == "SELECT COUNT(*) FROM event WHERE type = 'Meeting'"
    assert 'External Knowledge' not in r['prompt'] and 'CREATE TABLE "expense"' in r['prompt']
    assert r['answer'] == 'Câu lạc bộ đã tổ chức 18 buổi họp.'
    assert str(r['rows'][0][0]) in llm_fake.calls[1][0]  # prompt diễn giải chứa kết quả thật
    assert r['is_correct'] is None and r['gold_sql'] is None


def test_free_text_with_evidence(monkeypatch):
    monkeypatch.setattr(llm, 'call_llm', fake_llm('```sql\nSELECT 1\n```'))
    r = ask(question='x', evidence='meeting refers to type = "Meeting"')
    assert '-- External Knowledge: meeting refers to type = "Meeting"' in r['prompt']


def test_dev_question_correct(monkeypatch, conn):
    gold = conn.execute('SELECT gold_sql FROM dev_question WHERE id = 1379').fetchone()[0]
    monkeypatch.setattr(llm, 'call_llm', fake_llm(f'```sql\n{gold}\n```'))
    r = ask(dev_question_id=1379)
    assert r['status'] == 'EXECUTED' and r['is_correct'] == 1 and r['gold_sql'] == gold
    assert r['evidence_used'] and '-- External Knowledge:' in r['prompt']


def test_dev_question_without_evidence(monkeypatch):
    monkeypatch.setattr(llm, 'call_llm', fake_llm('```sql\nSELECT 1\n```'))
    r = ask(dev_question_id=1379, use_evidence=False)
    assert r['evidence_used'] is None and 'External Knowledge' not in r['prompt'] and r['is_correct'] == 0


def test_prompt_matches_benchmark_ollama(monkeypatch, conn):
    import ollama_request
    monkeypatch.setattr(llm, 'call_llm', fake_llm('```sql\nSELECT 1\n```'))
    q = conn.execute('SELECT * FROM dev_question WHERE id = 1379').fetchone()
    r = ask(dev_question_id=1379)
    assert r['prompt'] == ollama_request.generate_combined_prompts_one(config.SOURCE_DB, q['question'], q['evidence'])
    assert prompt.build_schema_part() == ollama_request.generate_schema_prompt(config.SOURCE_DB)


def test_gpt35_uses_same_prompt_as_chat_models(monkeypatch, conn):
    import ollama_request
    llm_fake = fake_llm("```sql\nSELECT COUNT(*) FROM event WHERE type = 'Meeting'\n```")
    monkeypatch.setattr(llm, 'call_llm', llm_fake)
    q = conn.execute('SELECT * FROM dev_question WHERE id = 1379').fetchone()
    r = client.post('/api/ask', json={'model_id': model_id('GPT-3.5-Turbo'), 'dev_question_id': 1379}).json()
    sql_prompt, sql_kw = llm_fake.calls[0]
    assert sql_prompt == ollama_request.generate_combined_prompts_one(config.SOURCE_DB, q['question'], q['evidence'])
    assert sql_kw == {'max_tokens': 256, 'stop': ['--', '\n\n', ';', '#']}
    assert r['sql'] == "SELECT COUNT(*) FROM event WHERE type = 'Meeting'"
    assert r['status'] == 'EXECUTED'


RAW_OUTPUTS = [
    "```sql\nSELECT COUNT(*) FROM event;\n```",
    "<think>đếm số sự kiện</think>\n```sql\nSELECT COUNT(*) FROM event\n```",
    "```sql\nSELECT name FROM member WHERE x = 1",   # khối ```sql bị cắt cụt
    "SELECT COUNT(*) FROM event; -- giải thích",
    "COUNT(*) FROM event",                          # GPT-3.5 viết tiếp sau "SELECT "
]


@pytest.mark.parametrize('raw', RAW_OUTPUTS)
def test_extract_sql_matches_benchmark(raw):
    import ollama_request
    import openai_request
    assert llm.extract_sql('ollama', raw) == ollama_request.extract_sql(raw)
    assert llm.extract_sql('openai', raw) == openai_request.extract_sql(raw)


def test_answer_none_when_llm_fails(monkeypatch):
    calls = []

    def sql_then_fail(model, prompt_text, **kw):
        calls.append(1)
        if len(calls) == 1:
            return "```sql\nSELECT COUNT(*) FROM event WHERE type = 'Meeting'\n```"
        raise llm.LLMError('model lỗi khi diễn giải')

    monkeypatch.setattr(llm, 'call_llm', sql_then_fail)
    r = ask(question='How many meetings?')
    assert r['status'] == 'EXECUTED' and r['answer'] is None


def test_llm_failure():
    r = ask(question='x?')
    assert r['status'] == 'FAILED_GENERATION' and 'không gọi model thật' in r['error'] and r['sql'] is None


def test_no_sql_generated(monkeypatch):
    monkeypatch.setattr(llm, 'call_llm', fake_llm('```sql\n```'))
    assert ask(question='x')['status'] == 'FAILED_GENERATION'


@pytest.mark.parametrize('sql', ['DELETE FROM member', 'DROP TABLE event', 'SELECT * FROM no_such_table'])
def test_bad_sql_is_exec_error(monkeypatch, sql):
    monkeypatch.setattr(llm, 'call_llm', fake_llm(f'```sql\n{sql}\n```'))
    assert ask(question='x')['status'] == 'EXEC_ERROR'  # CSDL mở chỉ đọc


def test_ask_requires_question():
    assert client.post('/api/ask', json={'model_id': 1}).status_code == 422


def test_dev_questions_loaded_from_dev_json():
    qs = client.get('/api/dev-questions').json()
    assert len(qs) == 158 and qs[0]['id'] == 1312 and qs[-1]['id'] == 1469
