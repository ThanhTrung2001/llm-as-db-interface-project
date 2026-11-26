"""Kiểm thử mục "Bên trong model": tokenizer BPE, giải nén Q4_K, và dữ liệu service.ask() trả về.
Không cần Ollama hay file model thật."""
import struct

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.backend import inside_model, llm
from app.backend.main import app

client = TestClient(app)


class FakeGGUF:
    """Bộ từ vựng đồ chơi: 'a', 'b' ghép thành 'ab'; ' ab' (byte-level 'Ġab') là một token."""
    meta = {'tokenizer.ggml.tokens': ['a', 'b', 'ab', 'Ġ', 'Ġab', '<|im_start|>'],
            'tokenizer.ggml.merges': ['a b', 'Ġ ab'],
            'tokenizer.ggml.token_type': [1, 1, 1, 1, 1, 3],
            'tokenizer.ggml.eos_token_id': 5}


def test_bpe_tokenize_and_decode():
    tok = inside_model.Tokenizer(FakeGGUF())
    toks = tok.encode('<|im_start|>ab ab')
    assert toks == [(5, '<|im_start|>'), (2, 'ab'), (4, ' ab')]  # token đặc biệt giữ nguyên, dấu cách dính vào từ
    assert tok.decode([i for i, _ in toks]) == '<|im_start|>ab ab'
    assert tok.id_of_bytes(list(b' ab')) == 4


def test_dequantize_q4_k():
    # d = 1, dmin = 0.5; 8 nhóm có scale = 1, min = 2  → giá trị = q − 1
    head = struct.pack('<ee', 1.0, 0.5)
    scales = bytes([1, 1, 1, 1, 2, 2, 2, 2, 0x21, 0x21, 0x21, 0x21])
    qs = bytes(range(128))
    out = inside_model.dequantize_q4_k(head + scales + qs)
    q = np.arange(128)
    expected = np.concatenate([np.concatenate([(q[32 * g:32 * g + 32] & 0xF), (q[32 * g:32 * g + 32] >> 4)])
                               for g in range(4)]) - 1.0
    assert out.shape == (256,) and np.allclose(out, expected)


def fake_call(model, prompt_text, trace=None, **kw):
    if trace is None:
        return 'ok'  # lần gọi diễn giải kết quả
    trace.update(endpoint='http://x/v1/chat/completions', request={'model': 'm'}, elapsed_ms=5,
                 finish_reason='stop', prompt_tokens=900, completion_tokens=2,
                 tokens=[{'token': 'SELECT', 'prob': 0.99, 'bytes': list(b'SELECT'),
                          'top': [{'token': 'SELECT', 'prob': 0.99}, {'token': 'WITH', 'prob': 0.01}]}])
    return '```sql\nSELECT 1;\n```'


def ask(**body):
    mid = next(m['id'] for m in client.get('/api/models').json() if m['name'] == 'Qwen2.5-Coder')
    return client.post('/api/ask', json={'model_id': mid, **body}).json()


def test_inside_without_model_file(monkeypatch):
    """Không mở được file model → vẫn có request + bước Decode (logprobs), kèm ghi chú."""
    monkeypatch.setattr(llm, 'call_llm', fake_call)
    monkeypatch.setattr(inside_model, 'load', lambda *a: None)
    r = ask(question='x')
    inside = r['inside']
    assert inside['request'].startswith('POST http://x/v1/chat/completions') and inside['note']
    assert [s['key'] for s in inside['steps']] == ['E']
    assert inside['steps'][0]['decode_rows'][0]['token'] == 'SELECT'
    assert r['extract_steps'][-1]['text'] == r['sql'] == 'SELECT 1'


def test_inside_empty_when_llm_fails():
    r = ask(question='x')  # fixture no_real_llm bên dưới → gọi model lỗi
    assert r['status'] == 'FAILED_GENERATION'
    assert r['inside'] == {'request': None, 'steps': [], 'note': None} and r['extract_steps'] == []


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    def offline(*a, **k):
        raise llm.LLMError('test: không gọi model thật')
    monkeypatch.setattr(llm, 'call_llm', offline)
