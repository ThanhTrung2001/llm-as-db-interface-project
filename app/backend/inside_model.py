"""
Chạy lại BẰNG TAY những gì model server (Ollama) làm với prompt, để thấy đầu ra thật của từng bước.

App chỉ gửi văn bản cho Ollama và nhận văn bản về. Bên trong Ollama, prompt đi qua:

    A. apply_template()   prompt (văn bản)          → văn bản có token đặc biệt <|im_start|>… (chuỗi model thật sự đọc)
    B. tokenize()         văn bản                   → dãy token ID, ví dụ "SELECT" → 4858
    C. embed()            token ID                  → vector 3.584 số thực (một dòng của ma trận embedding)
    D. (transformer)      ma trận n × 3.584         → ma trận n × 3.584 (28 tầng attention + FFN) — chỉ server làm
    E. (decode)           vector cuối               → xác suất cho 152.064 token → chọn token cao nhất → lặp
    F. detokenize()       dãy token ID sinh ra      → văn bản thô (chứa câu SQL)

A, B, C, F được chạy lại ở đây bằng chính dữ liệu trong file model (.gguf) mà Ollama dùng:
    - bộ từ vựng 152.064 token + 151.387 quy tắc ghép BPE   (metadata trong file gguf)
    - ma trận embedding token_embd.weight 152.064 × 3.584  (lưu dạng Q4_K, giải nén ở dequantize_q4_k)
rồi ĐỐI CHIẾU với server: số token tự đếm phải bằng usage.prompt_tokens, văn bản tự ghép phải bằng content.
D và E là phép nhân ma trận 7,6 tỷ tham số — chỉ server chạy; thứ nhìn được là kết quả của E (logprobs).

Chỉ áp dụng cho model chạy Ollama dùng template ChatML (Qwen2.5-Coder — model mặc định của demo).
"""
import re
import struct
from functools import lru_cache
from typing import Optional

import httpx
import numpy as np


# ======================= đọc file model .gguf =======================

GGUF_SCALAR = {0: 'B', 1: 'b', 2: 'H', 3: 'h', 4: 'I', 5: 'i', 6: 'f', 7: '?', 10: 'Q', 11: 'q', 12: 'd'}
GGML_Q4_K = 12          # kiểu lượng tử hoá của token_embd.weight trong qwen2.5-coder:7b (Q4_K_M)
Q4_K_BLOCK_BYTES = 144  # 256 số / block: d (2 byte) + dmin (2) + scales (12) + qs (128)


class GGUFFile:
    """Đọc phần đầu file .gguf: metadata (tokenizer) + vị trí từng tensor. Dữ liệu tensor đọc khi cần."""

    def __init__(self, path: str):
        self.path = path
        self.meta, self.tensors = {}, {}
        with open(path, 'rb') as f:
            rd = lambda fmt: struct.unpack('<' + fmt, f.read(struct.calcsize('<' + fmt)))[0]
            rstr = lambda: f.read(rd('Q')).decode('utf-8', 'replace')

            def rval(t):
                if t == 8:
                    return rstr()
                if t == 9:  # mảng
                    item_t, n = rd('I'), rd('Q')
                    if item_t == 8:
                        return [rstr() for _ in range(n)]
                    fmt = GGUF_SCALAR[item_t]
                    return list(struct.unpack(f'<{n}{fmt}', f.read(n * struct.calcsize(fmt))))
                return rd(GGUF_SCALAR[t])

            assert f.read(4) == b'GGUF', 'không phải file gguf'
            _version, n_tensors, n_kv = rd('I'), rd('Q'), rd('Q')
            for _ in range(n_kv):
                key = rstr()
                self.meta[key] = rval(rd('I'))
            infos = []
            for _ in range(n_tensors):
                name = rstr()
                dims = [rd('Q') for _ in range(rd('I'))]
                infos.append((name, dims, rd('I'), rd('Q')))
            align = self.meta.get('general.alignment', 32)
            data_start = (f.tell() + align - 1) // align * align
        for name, dims, typ, off in infos:
            self.tensors[name] = {'dims': dims, 'type': typ, 'offset': data_start + off}

    def read_rows(self, name: str, row_ids: list) -> np.ndarray:
        """Đọc các dòng của một ma trận Q4_K (mỗi dòng = vector của một token) và giải nén ra float32."""
        t = self.tensors[name]
        assert t['type'] == GGML_Q4_K, f'{name} không phải Q4_K'
        row_len = t['dims'][0]
        row_bytes = row_len // 256 * Q4_K_BLOCK_BYTES
        with open(self.path, 'rb') as f:
            rows = []
            for r in row_ids:
                f.seek(t['offset'] + r * row_bytes)
                rows.append(dequantize_q4_k(f.read(row_bytes)))
        return np.stack(rows)


def dequantize_q4_k(raw: bytes) -> np.ndarray:
    """Giải nén Q4_K (giống dequantize_row_q4_K của llama.cpp).

    Mỗi block 256 số = 8 nhóm × 32 số. Mỗi số lưu 4 bit q (0..15); giá trị thật = d·scale_nhóm·q − dmin·min_nhóm.
    """
    b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, Q4_K_BLOCK_BYTES)
    d = b[:, 0:2].copy().view(np.float16).astype(np.float32)     # (n, 1)
    dmin = b[:, 2:4].copy().view(np.float16).astype(np.float32)  # (n, 1)
    sc, qs = b[:, 4:16].astype(np.int32), b[:, 16:].astype(np.int32)
    scales, mins = np.empty((len(b), 8), np.int32), np.empty((len(b), 8), np.int32)
    for j in range(8):  # 8 cặp (scale, min) 6-bit nén trong 12 byte
        if j < 4:
            scales[:, j], mins[:, j] = sc[:, j] & 63, sc[:, j + 4] & 63
        else:
            scales[:, j] = (sc[:, j + 4] & 0xF) | ((sc[:, j - 4] >> 6) << 4)
            mins[:, j] = (sc[:, j + 4] >> 4) | ((sc[:, j] >> 6) << 4)
    out = np.empty((len(b), 256), np.float32)
    for g in range(4):  # 32 byte qs → 32 số (4 bit thấp) + 32 số (4 bit cao)
        q = qs[:, 32 * g:32 * g + 32]
        out[:, 64 * g:64 * g + 32] = d * scales[:, [2 * g]] * (q & 0xF) - dmin * mins[:, [2 * g]]
        out[:, 64 * g + 32:64 * g + 64] = d * scales[:, [2 * g + 1]] * (q >> 4) - dmin * mins[:, [2 * g + 1]]
    return out.reshape(-1)


# ======================= tokenizer BPE (byte-level, kiểu GPT-2 / Qwen2) =======================

def _bytes_to_unicode() -> dict:
    """Byte 0..255 → một ký tự in được (byte-level BPE). Ví dụ dấu cách 0x20 → 'Ġ', xuống dòng 0x0A → 'Ċ'."""
    bs = list(range(ord('!'), ord('~') + 1)) + list(range(ord('¡'), ord('¬') + 1)) + list(range(ord('®'), ord('ÿ') + 1))
    cs, n = bs[:], 0
    for x in range(256):
        if x not in bs:
            bs.append(x)
            cs.append(256 + n)
            n += 1
    return dict(zip(bs, map(chr, cs)))


BYTE_ENC = _bytes_to_unicode()
BYTE_DEC = {v: k for k, v in BYTE_ENC.items()}

# Tách thô trước khi BPE (pre-tokenizer "qwen2"): chữ, từng chữ số, cụm dấu, khoảng trắng...
# \p{L} (chữ) viết bằng [^\W\d_], \p{N} (số) viết bằng \d vì module re không có \p{...}
PRETOKENIZE_RE = re.compile(
    r"(?i:'s|'t|'re|'ve|'m|'ll|'d)|(?:[^\w\r\n]|_)?[^\W\d_]+|\d| ?(?:[^\s\w]|_)+[\r\n]*|\s*[\r\n]+|\s+(?!\S)|\s+")


class Tokenizer:
    def __init__(self, g: GGUFFile):
        self.tokens = g.meta['tokenizer.ggml.tokens']             # id → chuỗi (dạng byte-level)
        self.vocab = {t: i for i, t in enumerate(self.tokens)}    # chuỗi → id
        self.ranks = {tuple(m.split(' ', 1)): i for i, m in enumerate(g.meta['tokenizer.ggml.merges'])}
        types = g.meta.get('tokenizer.ggml.token_type') or []
        specials = [self.tokens[i] for i, t in enumerate(types) if t in (3, 4)]  # 3 = control, 4 = user-defined
        self.special_re = re.compile('(' + '|'.join(map(re.escape, sorted(specials, key=len, reverse=True))) + ')')
        self.eos_id = g.meta.get('tokenizer.ggml.eos_token_id')

    def _bpe(self, word: str) -> list:
        """Ghép dần các cặp ký tự kề nhau theo thứ hạng merge (cặp hay gặp nhất ghép trước) tới khi hết cặp ghép được."""
        parts = list(word)
        while len(parts) > 1:
            rank, i = min((self.ranks.get((parts[i], parts[i + 1]), float('inf')), i) for i in range(len(parts) - 1))
            if rank == float('inf'):
                break
            parts[i:i + 2] = [parts[i] + parts[i + 1]]
        return parts

    def encode(self, text: str) -> list:
        """Văn bản → [(id, mảnh văn bản), ...]. Token đặc biệt (<|im_start|>...) giữ nguyên thành 1 token."""
        out = []
        for seg in self.special_re.split(text):
            if not seg:
                continue
            if seg in self.vocab and self.special_re.fullmatch(seg):
                out.append((self.vocab[seg], seg))
                continue
            for piece in PRETOKENIZE_RE.findall(seg):
                for p in self._bpe(''.join(BYTE_ENC[b] for b in piece.encode('utf-8'))):
                    out.append((self.vocab[p], self.piece_text(p)))
        return out

    @staticmethod
    def piece_text(p: str) -> str:
        return bytes(BYTE_DEC[c] for c in p).decode('utf-8', 'replace')

    def id_of_bytes(self, bs: list) -> Optional[int]:
        """Token server trả về (dạng byte) → id trong từ vựng."""
        return self.vocab.get(''.join(BYTE_ENC[b] for b in bs))

    def decode(self, ids: list) -> str:
        """Dãy id → văn bản: mỗi id → chuỗi byte của nó, nối lại, giải mã UTF-8."""
        return b''.join(bytes(BYTE_DEC[c] for c in self.tokens[i]) for i in ids).decode('utf-8', 'replace')


# ======================= model đang chạy trong Ollama =======================

class OllamaModel:
    def __init__(self, base_url: str, model_tag: str):
        root = re.sub(r'/v1/?$', '', base_url or '')
        show = httpx.post(f'{root}/api/show', json={'model': model_tag}, timeout=15).json()
        path = re.search(r'^FROM (.+)$', show['modelfile'], re.M).group(1).strip()  # file .gguf Ollama đang dùng
        self.template, self.system = show.get('template') or '', show.get('system')
        self.gguf = GGUFFile(path)
        self.tok = Tokenizer(self.gguf)
        arch = self.gguf.meta['general.architecture']
        self.n_layers = self.gguf.meta.get(f'{arch}.block_count')
        self.dim = self.gguf.meta.get(f'{arch}.embedding_length')

    @property
    def is_chatml(self) -> bool:
        return '<|im_start|>' in self.template

    def apply_template(self, prompt: str) -> str:
        """A. Bọc prompt theo template ChatML của Qwen (nhánh .Messages: system mặc định + 1 tin user)."""
        system = f'<|im_start|>system\n{self.system}<|im_end|>\n' if self.system else ''
        return f'{system}<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n'

    def tokenize(self, text: str) -> list:
        """B. Văn bản → [(token id, mảnh văn bản)]."""
        return self.tok.encode(text)

    def embed(self, ids: list) -> np.ndarray:
        """C. Mỗi token id → tra đúng dòng đó trong ma trận embedding → ma trận len(ids) × 3.584."""
        return self.gguf.read_rows('token_embd.weight', ids)

    def detokenize(self, ids: list) -> str:
        """F. Dãy token id model sinh ra → văn bản."""
        return self.tok.decode(ids)


@lru_cache(maxsize=4)
def load(base_url: str, model_tag: str) -> Optional[OllamaModel]:
    """Mở model một lần rồi giữ lại (đọc metadata tokenizer mất khoảng 1–2 giây). None nếu không đọc được."""
    try:
        m = OllamaModel(base_url, model_tag)
        return m if m.is_chatml else None
    except Exception:
        return None
