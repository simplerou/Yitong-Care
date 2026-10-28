// 原设计中的浏览器演示算法；后端接入时由 API 替代。
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;", "'":"&#39;"}[c]));
export function splitSents(text) {
    return text.split(/(?<=[。！？；])/).map((s) => s.trim()).filter(Boolean);
  }
export function chunkText(text, size, overlap) {
    const clean = String(text || "").replace(/\r/g, "").trim();
    if (!clean) return [];
    const sents = clean.split(/(?<=[。！？；\n])/).map((s) => s.trim()).filter(Boolean);
    const out = [];
    let buf = "";
    for (let s of sents) {
      while (s.length > size) {
        if (buf) { out.push(buf); buf = ""; }
        out.push(s.slice(0, size).trim());
        s = s.slice(size).trim();
      }
      if (!s) continue;
      if (buf && (buf + s).length > size) {
        out.push(buf.trim());
        // 重叠区按整句回退，避免新片段从半个句子开始
        let tail = "";
        if (overlap > 0) {
          const prev = splitSents(buf);
          for (let k = prev.length - 1; k >= 0; k--) {
            if ((prev[k] + tail).length > overlap) break;
            tail = prev[k] + tail;
          }
        }
        buf = (tail + s).trim();
      } else {
        buf = (buf + s).trim();
      }
    }
    if (buf.trim()) out.push(buf.trim());
    return out.filter(Boolean);
  }

  /* ---------------------- 向量化（哈希 n-gram，演示用） ---------------------- */
  const DIM = 384;
export function hashTok(str, seed) {
    let h = (2166136261 ^ seed) >>> 0;
    for (let i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }
export function embed(text) {
    const v = new Float32Array(DIM);
    const clean = String(text).replace(/[^\u4e00-\u9fa5a-zA-Z0-9]/g, "");
    for (let i = 0; i < clean.length; i++) {
      v[hashTok(clean[i], 17) % DIM] += 0.45;
      if (i < clean.length - 1) v[hashTok(clean.slice(i, i + 2), 31) % DIM] += 1;
    }
    let n = 0;
    for (let i = 0; i < DIM; i++) n += v[i] * v[i];
    n = Math.sqrt(n) || 1;
    for (let i = 0; i < DIM; i++) v[i] /= n;
    return v;
  }
export function cosine(a, b) {
    let s = 0;
    for (let i = 0; i < DIM; i++) s += a[i] * b[i];
    return s;
  }
export function bigrams(str) {
    const s = String(str).replace(/[\s，。！？；：、,.!?;:"'（）()【】]/g, "");
    const set = new Set();
    for (let i = 0; i < s.length - 1; i++) set.add(s.slice(i, i + 2));
    if (!set.size && s) set.add(s);
    return [...set];
  }


  const STOP = new Set(["什么", "怎么", "可以", "是否", "需要", "哪些", "多少", "如何", "请问", "一下",
    "我们", "这个", "那个", "有没", "以及", "还是", "就是", "如果", "因为", "所以", "那么", "现在",
    "今天", "最近", "老人", "老年", "应该", "怎样", "一个", "哪些", "有哪", "么办"]);
export function queryTerms(q) {
    const segs = String(q).toLowerCase()
      .split(/[\s，。；：、,.!?;:"'（）()【】\[\]·]+/)
      .filter((s) => s.length >= 2);
    const out = new Set();
    segs.forEach((s) => {
      out.add(s);
      for (let i = 0; i < s.length - 1; i++) {
        const g = s.slice(i, i + 2);
        if (!STOP.has(g)) out.add(g);
      }
    });
    return [...out].sort((a, b) => b.length - a.length).slice(0, 16);
  }
  const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
export function highlight(text, q) {
    const safe = esc(text);
    const terms = queryTerms(q);
    if (!terms.length) return safe;
    try {
      const re = new RegExp("(" + terms.map(escapeRe).join("|") + ")", "gi");
      return safe.replace(re, "<mark>$1</mark>");
    } catch (e) { return safe; }
  }
export function firstMatch(text, q) {
    const lower = text.toLowerCase();
    const terms = queryTerms(q);
    let best = -1;
    terms.forEach((t) => {
      const i = lower.indexOf(t);
      if (i >= 0 && (best < 0 || i < best)) best = i;
    });
    return best;
  }


export function scorePct(score, top) {
    const base = top || Math.max(score, 0.4);
    const ratio = Math.max(0, Math.min(1, score / base));
    return Math.max(38, Math.min(97, Math.round(45 + 52 * Math.pow(ratio, 2.2))));
  }

export function snippetHTML(text, q, len = 190) {
    const idx = firstMatch(text, q);
    let start = idx > 50 ? idx - 50 : 0;
    let s = text.slice(start, start + len);
    return (start > 0 ? "…" : "") + highlight(s, q) + (start + len < text.length ? "…" : "");
  }

