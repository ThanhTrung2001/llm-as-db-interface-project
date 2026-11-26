// ClubQuery — đa ngôn ngữ (EN/VI) mà không phải sửa từng view.
// Mã nguồn vẫn viết chuỗi tiếng Anh; module này dịch chữ trên DOM ngay khi nó xuất hiện.
// Thêm ngôn ngữ mới: tạo file xx.js giống vi.js rồi đăng ký vào PACKS và LANGS.
import { DICT as VI, PATTERNS as VI_PATTERNS } from './vi.js';

const PACKS = { vi: { dict: VI, patterns: VI_PATTERNS } };
export const LANGS = [['en', 'EN'], ['vi', 'VI']];

let lang = 'en';
try { lang = localStorage.getItem('cq_lang') || 'en'; } catch { /* bộ nhớ trình duyệt bị chặn */ }
if (lang !== 'en' && !PACKS[lang]) lang = 'en';
export const getLang = () => lang;
export function setLang(l) {
  try { localStorage.setItem('cq_lang', l); } catch {}
  location.reload(); // nạp lại trang; token vẫn còn nên không phải đăng nhập lại
}

const pack = PACKS[lang];
const missing = new Set();

// Dịch một chuỗi; dùng được trực tiếp trong JS: t('Save')
export function t(s) {
  if (!pack || s == null) return s;
  const key = String(s).trim();
  if (!key) return s;
  if (pack.dict[key] != null) return pack.dict[key];
  for (const [re, fn] of pack.patterns) { const m = key.match(re); if (m) return fn(m, t); }
  if (/[A-Za-z]{2}/.test(key)) missing.add(key);
  return s;
}

// Không dịch SQL, code, ô nhập liệu, hoặc phần tử có thuộc tính data-no-i18n
const SKIP = 'script,style,code,pre,textarea,[data-no-i18n],[contenteditable]';
const ATTRS = ['title', 'aria-label', 'placeholder'];

function translateText(node) {
  const p = node.parentElement;
  if (!p || p.closest(SKIP)) return;
  const raw = node.nodeValue, key = raw.trim();
  if (!key) return;
  const out = t(key);
  if (out !== key) node.nodeValue = raw.replace(key, out);
}
function translateAttrs(el) {
  if (el.closest(SKIP)) return;
  for (const a of ATTRS) {
    const v = el.getAttribute(a);
    if (v) { const out = t(v); if (out !== v) el.setAttribute(a, out); }
  }
}
function translateTree(root) {
  if (root.nodeType === Node.TEXT_NODE) return translateText(root);
  if (root.nodeType !== Node.ELEMENT_NODE) return;
  translateAttrs(root);
  root.querySelectorAll('[title],[aria-label],[placeholder]').forEach(translateAttrs);
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n; (n = w.nextNode());) translateText(n);
}

if (pack) {
  document.documentElement.lang = lang;
  translateTree(document.documentElement);
  new MutationObserver((muts) => {
    for (const m of muts) {
      if (m.type === 'childList') m.addedNodes.forEach(translateTree);
      else if (m.type === 'characterData') translateText(m.target);
      else if (m.type === 'attributes') translateAttrs(m.target);
    }
  }).observe(document.documentElement, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS });
}

// Gõ cqMissing() trong Console (F12) để in ra các chuỗi chưa có bản dịch, dán vào vi.js rồi điền nghĩa
window.cqMissing = () => {
  const a = [...missing].sort();
  console.log(a.map((s) => `  '${s.replace(/'/g, "\\'")}': '',`).join('\n'));
  return a.length;
};
