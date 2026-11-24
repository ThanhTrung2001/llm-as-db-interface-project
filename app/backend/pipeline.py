"""
Dựng mục "Bên trong model" trên giao diện — nằm giữa "Prompt gửi cho LLM" và "Văn bản thô model trả về".

    Prompt gửi cho LLM (văn bản 2.600 ký tự)
        │  0. app gửi HTTP POST /v1/chat/completions                                   ← llm.call_llm
        ▼  ─────────────── từ đây là bên trong Ollama ───────────────
    A. Template     prompt → chuỗi có <|im_start|>user …<|im_end|> <|im_start|>assistant   ← inside_model.apply_template
    B. Tokenize     chuỗi → 606 token ID, ví dụ " SQLite" → 28334                       ← inside_model.tokenize
    C. Embedding    mỗi ID → vector 3.584 số, ví dụ 28334 → [0.012, -0.031, …]          ← inside_model.embed
    D. Transformer  ma trận 606 × 3.584 → qua 28 tầng → ma trận 606 × 3.584              (chỉ server chạy)
    E. Decode       vector cuối → xác suất cho 152.064 token → chọn cao nhất → lặp        (logprobs server trả)
    F. Detokenize   các ID sinh ra → văn bản                                              ← inside_model.detokenize
        ▼  ─────────────── server trả JSON về app ───────────────
    Văn bản thô model trả về  ("```sql\\nSELECT …\\n```")

A, B, C, F: chạy lại bằng chính file model Ollama dùng, và ĐỐI CHIẾU với server (số token, văn bản).
Mỗi bước: {key, title, io, explain, code, check, + dữ liệu để vẽ}. Lời trình bày: docs/VAN_NOI_DEMO.md.
"""
import json
from typing import Optional

import numpy as np

from . import inside_model

MAX_EMBED_ROWS = 16  # số token (của câu hỏi) hiện vector embedding
EMBED_HEAD = 8       # số phần tử đầu của mỗi vector được hiện


def build_inside(prompt: Optional[str], llm_output: Optional[str], question: str, model: dict, trace: dict) -> dict:
    """Trả về {'request', 'steps', 'note'} cho mục "Bên trong model". trace do llm.call_llm ghi."""
    if not prompt or not trace:
        return {'request': None, 'steps': [], 'note': None}
    request = f"POST {trace['endpoint']}\n" + json.dumps(trace['request'], ensure_ascii=False, indent=2)
    gen = trace.get('tokens') or []
    m = inside_model.load(model['base_url'], model['model_tag']) if model['provider'] == 'ollama' else None
    if m is None:
        note = ('Chỉ chạy lại được các bước bên trong với model chạy Ollama dùng template ChatML (Qwen2.5-Coder). '
                'Model này chạy ở server ngoài nên chỉ xem được kết quả bước Decode (nếu server trả logprobs).')
        return {'request': request, 'steps': [step_decode(gen, None, trace)] if gen else [], 'note': note}

    text = m.apply_template(prompt)
    toks = m.tokenize(text)
    steps = [step_template(m, prompt, text), step_tokenize(m, text, toks, trace),
             step_embed(m, text, toks, question), step_transformer(m, toks),
             step_decode(gen, m, trace), step_detokenize(m, gen, llm_output)]
    return {'request': request, 'steps': steps, 'note': None}


# ---------------------------------------------------------------- A
def step_template(m, prompt: str, text: str) -> dict:
    start = text.index(prompt)
    before, after = text[:start], text[start + len(prompt):]
    return {
        'key': 'A', 'title': 'Template: bọc prompt thành hội thoại',
        'io': f'Prompt {len(prompt):,} ký tự → chuỗi {len(text):,} ký tự có token đặc biệt',
        'explain': 'Qwen được huấn luyện trên hội thoại dạng ChatML, mỗi lượt nói mở bằng <|im_start|>vai_trò và '
                   'đóng bằng <|im_end|>. Ollama thêm system prompt mặc định, bọc prompt vào lượt "user", rồi mở sẵn '
                   'lượt "assistant" để model viết tiếp. Phần tô màu là phần Ollama thêm vào.',
        'code': 'inside_model.OllamaModel.apply_template()',
        'template': {'before': before, 'prompt_len': len(prompt), 'prompt_tail': prompt[-160:], 'after': after},
    }


# ---------------------------------------------------------------- B
def step_tokenize(m, text: str, toks: list, trace: dict) -> dict:
    server_n = trace.get('prompt_tokens')
    vocab = len(m.tok.tokens)
    return {
        'key': 'B', 'title': 'Tokenize: văn bản → dãy số (token ID)',
        'io': f'Chuỗi {len(text):,} ký tự → {len(toks):,} token ID (mỗi ID là số nguyên 0…{vocab - 1:,})',
        'explain': f'Tokenizer BPE có bộ từ vựng {vocab:,} mảnh. Đầu tiên tách thô văn bản thành từ, số, dấu câu, '
                   'khoảng trắng. Sau đó ghép dần các byte theo 151.387 quy tắc merge (cặp nào hay gặp hơn thì ghép '
                   'trước) cho tới khi không ghép được nữa. Mỗi mảnh cuối cùng là một token có ID riêng. Dấu cách '
                   'thường dính vào đầu từ (" SELECT" khác "SELECT"). Token đặc biệt như <|im_start|> luôn là 1 token. '
                   'Rê chuột lên một ô để xem ID.',
        'code': 'inside_model.OllamaModel.tokenize() → Tokenizer.encode() (_bpe)',
        'check': {'ok': len(toks) == server_n,
                  'text': f'Tự đếm: {len(toks):,} token · Server báo (usage.prompt_tokens): {server_n:,}'},
        'tokens': [[i, p, p.startswith('<|')] for i, p in toks],
    }


# ---------------------------------------------------------------- C
def step_embed(m, text: str, toks: list, question: str) -> dict:
    # chọn các token thuộc câu hỏi (dòng "-- <câu hỏi>" trong prompt) để hiện vector
    q_start = text.encode().rfind(question.encode())
    pos, rows = 0, []
    for i, p in toks:
        end = pos + len(p.encode())
        if q_start >= 0 and end > q_start and len(rows) < MAX_EMBED_ROWS and not p.startswith('<|'):
            rows.append((i, p))
        pos = end
    rows = rows or [t for t in toks if not t[1].startswith('<|')][:MAX_EMBED_ROWS]
    E = m.embed([i for i, _ in rows])
    d = m.dim
    return {
        'key': 'C', 'title': 'Embedding: mỗi token ID → một vector số thực',
        'io': f'{len(toks):,} token ID → ma trận {len(toks):,} × {d:,} = {len(toks) * d:,} số thực',
        'explain': f'Ma trận embedding có {len(m.tok.tokens):,} dòng × {d:,} cột, mỗi dòng ứng với một token. '
                   'Token ID chỉ là số thứ tự dòng: "embedding" ở đây là bước tra bảng, chưa có phép tính nào. Các con '
                   'số này học được lúc huấn luyện; token có nghĩa gần nhau thì vector gần nhau. Bảng dưới là vector '
                   'thật của các token trong câu hỏi, đọc thẳng từ file model (lưu nén 4-bit Q4_K, đã giải nén).',
        'code': "inside_model.OllamaModel.embed() → GGUFFile.read_rows('token_embd.weight') → dequantize_q4_k()",
        'embed_dim': d,
        'embed_rows': [{'id': i, 'piece': p, 'head': [round(float(x), 4) for x in v[:EMBED_HEAD]],
                        'norm': round(float(np.linalg.norm(v)), 3)} for (i, p), v in zip(rows, E)],
    }


# ---------------------------------------------------------------- D
def step_transformer(m, toks: list) -> dict:
    meta, arch = m.gguf.meta, m.gguf.meta['general.architecture']
    g = lambda k: meta.get(f'{arch}.{k}')
    n, d, L = len(toks), m.dim, m.n_layers
    return {
        'key': 'D', 'title': f'Transformer: {L} tầng xử lý cả prompt (prefill)',
        'io': f'Ma trận {n:,} × {d:,} → {L} tầng → ma trận {n:,} × {d:,} (cùng kích thước, đã "hiểu" ngữ cảnh)',
        'explain': f'Mỗi tầng có 2 phần. (1) Self-attention với {g("attention.head_count")} head: mỗi token so với '
                   'mọi token đứng trước nó để lấy thông tin (minh hoạ: token "meeting" trong câu hỏi có thể chú ý '
                   'tới cột "type" của bảng event). (2) Mạng feed-forward '
                   f'{d:,} → {g("feed_forward_length"):,} → {d:,}. {n:,} token được tính song song trong một lượt, '
                   'và các key/value attention được giữ lại (KV cache). Đây là phần tốn tính toán nhất. Ollama không '
                   'xuất giá trị trung gian, nên ở đây chỉ hiện kích thước.',
        'code': '(bên trong Ollama / llama.cpp — không gọi lại được từ Python)',
        'facts': {'Số tầng': L, 'Attention head': g('attention.head_count'),
                  'KV head (grouped-query attention)': g('attention.head_count_kv'),
                  'Chiều feed-forward': g('feed_forward_length'), 'Context tối đa': g('context_length'),
                  'Tổng số tham số': meta.get('general.parameter_count')},
    }


# ---------------------------------------------------------------- E
def step_decode(gen: list, m, trace: dict) -> dict:
    rows = []
    for k, t in enumerate(gen):
        tid = m.tok.id_of_bytes(t['bytes']) if (m and t.get('bytes')) else None
        rows.append({'step': k + 1, 'token': t['token'], 'id': tid, 'prob': t['prob'], 'top': t['top']})
    n_server = trace.get('completion_tokens')
    eos = (f' Token thứ {n_server} (không có trong logprobs) là <|im_end|> (ID {m.tok.eos_id:,}): model tự quyết định '
           'dừng, server thấy token này thì ngừng sinh.') if (m and n_server and n_server == len(gen) + 1) else ''
    vocab = f'{len(m.tok.tokens):,}' if m else 'toàn bộ'
    return {
        'key': 'E', 'title': 'Decode: sinh câu trả lời từng token một',
        'io': f'Vector cuối → xác suất cho {vocab} token → chọn 1 token → lặp {len(gen)} lần '
              f'(finish_reason = {trace.get("finish_reason")}, {trace.get("elapsed_ms", 0):,} ms)',
        'explain': f'Lấy vector của token cuối ở tầng cuối, nhân với ma trận đầu ra (LM head) để ra {vocab} điểm số, '
                   'mỗi điểm ứng với một token trong từ vựng. Softmax đổi điểm số thành xác suất. Vì temperature = 0 '
                   'nên luôn chọn token có xác suất cao nhất. Token vừa chọn được nối vào chuỗi và đi qua '
                   f'{m.n_layers if m else "các"} tầng (chỉ cần tính cho 1 token mới nhờ KV cache), rồi lặp lại. Bảng '
                   'dưới là dữ liệu thật server trả (logprobs), gồm 5 ứng viên cao nhất ở mỗi bước. Dòng vàng là chỗ '
                   'model phân vân.' + eos,
        'code': "llm.call_llm(trace=…) xin logprobs=True, top_logprobs=5 → trace['tokens']",
        'decode_rows': rows,
    }


# ---------------------------------------------------------------- F
def step_detokenize(m, gen: list, llm_output: Optional[str]) -> dict:
    ids = [m.tok.id_of_bytes(t['bytes']) for t in gen if t.get('bytes')]
    ok_ids = bool(ids) and None not in ids
    text = m.detokenize(ids) if ok_ids else None
    return {
        'key': 'F', 'title': 'Detokenize: dãy ID → văn bản',
        'io': f'{len(ids)} token ID → văn bản {len(text or ""):,} ký tự (chính là "Văn bản thô model trả về")',
        'explain': 'Mỗi ID được đổi ngược về chuỗi byte của nó trong từ vựng, nối lại rồi giải mã UTF-8. Đây là bước '
                   'duy nhất đi ngược từ số về chữ. Không có "embedding ngược": đầu ra của model là xác suất trên các '
                   'token (bước E), không phải vector được dịch ngược thành câu.',
        'code': 'inside_model.OllamaModel.detokenize() → Tokenizer.decode()',
        'check': {'ok': ok_ids and text == llm_output,
                  'text': 'Văn bản tự ghép từ token ID ' + ('= văn bản server trả về' if ok_ids and text == llm_output
                                                            else '≠ văn bản server trả về')},
        'ids': ids,
    }
