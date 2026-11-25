"""Gọi dịch vụ LLM. Ollama, Groq, OpenRouter đều có API chuẩn Chat Completions → dùng chung thư viện client `openai`."""
import os
import time

from dotenv import load_dotenv
from openai import OpenAI

from . import config, trace  # config: thêm BIRD_SRC vào sys.path
from ollama_request import extract_sql  # tách SQL khỏi ```sql ...``` như lúc benchmark Ollama

load_dotenv(os.path.join(config.ROOT, '.env'))


class LLMError(Exception):
    pass


def _mask(key: str) -> str:
    return key if key == 'ollama' or len(key) < 10 else f'{key[:4]}…{key[-4:]} ({len(key)} ký tự)'


def complete(model: dict, prompt: str, max_tokens: int = 512, timeout_s: float = 120,
             label: str = '2b.5a', stop: list = None) -> str:
    api_key = os.environ.get(model['api_key_env'] or '', '') or 'ollama'
    params = [
        ('model.provider', model['provider'], 'Nhà cung cấp: ollama | groq | openrouter'),
        ('model.model_tag', model['model_tag'], 'Tên model gửi trong request (chat.completions.create(model=...))'),
        ('model.base_url', model['base_url'], 'Địa chỉ API chuẩn Chat Completions. '
                                              'Ollama: http://localhost:11434/v1'),
        ('model.api_key_env', model['api_key_env'], 'Tên biến môi trường chứa khoá API (đọc từ .env)'),
        ('api_key', _mask(api_key), 'Khoá thật (đã che); "ollama" = không cần khoá'),
        ('messages', [{'role': 'user', 'content': f'<prompt {len(prompt)} ký tự, xem bước trước>'}],
         'Một tin nhắn user duy nhất chứa toàn bộ prompt'),
        ('temperature', 0, 'Bằng 0 → model chọn token chắc nhất, kết quả ổn định, lặp lại được (như benchmark)'),
        ('max_tokens', max_tokens, 'Số token tối đa model được sinh ra'),
        ('stop', stop, 'Gặp một trong các chuỗi này thì model dừng sinh (chuỗi dừng không nằm trong output); '
                       'None = không dùng'),
        ('timeout_s', timeout_s, 'Hết thời gian chờ (giây) thì báo lỗi LLMError'),
    ]
    if model['provider'] != 'ollama' and api_key == 'ollama':
        err = f'API key not configured ({model["api_key_env"]}) in .env'
        trace.step(label, 'llm.complete', 'Gọi LLM qua API Chat Completions', params,
                   f'LLMError: {err}')
        raise LLMError(err)
    started = time.monotonic()
    try:
        client = OpenAI(api_key=api_key, base_url=model['base_url'] or None, timeout=timeout_s)
        resp = client.chat.completions.create(
            model=model['model_tag'],
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0,
            max_tokens=max_tokens,
            **({'stop': stop} if stop else {}),
        )
    except Exception as e:  # mạng, khoá sai, model chưa pull...
        trace.step(label, 'llm.complete', 'Gọi LLM qua API Chat Completions', params,
                   f'LLMError: Lỗi gọi model: {e}')
        raise LLMError(f'Model call failed: {e}') from e
    content = resp.choices[0].message.content or ''
    usage = getattr(resp, 'usage', None)
    trace.step(
        label, 'llm.complete',
        'Gọi LLM qua API Chat Completions (cùng một client cho Ollama, Groq), nhận văn bản trả lời.',
        params, content,
        output_desc='Văn bản thô model trả về (resp.choices[0].message.content)',
        note=(f'thời gian gọi {int((time.monotonic() - started) * 1000)} ms; finish_reason='
              f'{resp.choices[0].finish_reason}; usage: prompt_tokens={getattr(usage, "prompt_tokens", None)}, '
              f'completion_tokens={getattr(usage, "completion_tokens", None)}'))
    return content


def generate_sql(model: dict, prompt: str, timeout_s: float = 120) -> str:
    raw = complete(model, prompt, timeout_s=timeout_s)
    sql = extract_sql(raw)
    final = '' if sql == 'SELECT' else sql  # extract_sql trả "SELECT" khi rỗng
    trace.step('2b.5b', 'ollama_request.extract_sql',
               'Tách câu SQL khỏi văn bản của model: bỏ <think>...</think>, lấy nội dung trong ```sql ... ```, '
               'cắt ở dấu ";" đầu tiên (cùng hàm với lúc benchmark).',
               [('raw_text', raw, 'Output của llm.complete ở bước trước')],
               final, output_desc='SQL model sinh ra; chuỗi rỗng = model không sinh được SQL')
    return final
