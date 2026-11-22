/* 銘柄メモ — 株ログの全タブで銘柄名の右に ● を出し、押すとメモを読み書きできる。
 *
 * データの正本: docs/data_memo/memos.json (Claude は memo.py で追記して push する)
 * ブラウザからの保存:
 *   - GitHubトークンを設定済み → GitHub API で memos.json を直接コミット(全端末に反映)
 *   - 未設定 → この端末の localStorage にだけ保存(「未同期」と表示。後でトークンを入れると送信される)
 * ● 赤 = メモあり / 青 = メモなし
 * 同一オリジンの iframe(他リポジトリのタブも al00000000.github.io なので同一)にも親から差し込む。
 */
(function () {
  "use strict";

  // iframe の中で読み込まれたら、親の StockMemo を共有する(データとモーダルを1つにするため)
  try {
    if (window.parent !== window && window.parent.StockMemo) {
      window.StockMemo = window.parent.StockMemo;
      window.StockMemo.attach(document);
      return;
    }
  } catch (e) { /* 別オリジン: 単体で動く */ }

  const REPO = "AL00000000/kabulog";
  const PATH = "docs/data_memo/memos.json";
  const scriptSrc = (document.currentScript && document.currentScript.src) || location.href;
  const DATA_URL = new URL("data_memo/memos.json", scriptSrc).href;
  const LS_PENDING = "kabulog_memo_pending";
  const LS_TOKEN = "kabulog_gh_token";
  const CODE_RE = /^[0-9][0-9][0-9][0-9A-Z]$/;

  let repo = { lists: {}, stocks: {} };   // memos.json の中身
  let loaded = false;
  const listeners = [];

  const readPending = () => { try { return JSON.parse(localStorage.getItem(LS_PENDING)) || {}; } catch (e) { return {}; } };
  const writePending = o => { try { localStorage.setItem(LS_PENDING, JSON.stringify(o)); } catch (e) { /* 保存できない環境 */ } };
  const token = () => { try { return localStorage.getItem(LS_TOKEN) || ""; } catch (e) { return ""; } };

  function stocks() {
    const out = Object.assign({}, repo.stocks || {});
    const p = readPending();
    for (const [c, v] of Object.entries(p)) { if (v === null) delete out[c]; else out[c] = v; }
    return out;
  }
  function get(code) { return stocks()[code] || null; }
  function hasMemo(code) {
    const s = get(code);
    return !!(s && ((s.notes && s.notes.length) || s.list || (s.reason && s.reason.trim())));
  }
  function isEmpty(s) { return !s || (!(s.notes && s.notes.length) && !s.list && !(s.reason && s.reason.trim())); }

  /* ---------- 読み込み ---------- */
  const b64dec = b => new TextDecoder().decode(Uint8Array.from(atob(b.replace(/\n/g, "")), c => c.charCodeAt(0)));
  const b64enc = s => { const u = new TextEncoder().encode(s); let bin = ""; for (const x of u) bin += String.fromCharCode(x); return btoa(bin); };

  async function apiGet() {
    const r = await fetch("https://api.github.com/repos/" + REPO + "/contents/" + PATH + "?ref=main&t=" + Date.now(), {
      headers: { Authorization: "Bearer " + token(), Accept: "application/vnd.github+json" }, cache: "no-store" });
    if (r.status === 404) return { data: { lists: {}, stocks: {} }, sha: null };
    if (!r.ok) throw new Error("GitHub API " + r.status);
    const j = await r.json();
    return { data: JSON.parse(b64dec(j.content)), sha: j.sha };
  }

  async function load() {
    try {
      if (token()) { repo = (await apiGet()).data; }
      else {
        const r = await fetch(DATA_URL + "?t=" + Date.now(), { cache: "no-store" });
        if (r.ok) repo = await r.json();
      }
    } catch (e) {
      try { const r = await fetch(DATA_URL + "?t=" + Date.now(), { cache: "no-store" }); if (r.ok) repo = await r.json(); } catch (e2) { /* 表示だけ続ける */ }
    }
    // 正本に反映済みの未同期分は消す
    const p = readPending();
    let changed = false;
    for (const [c, v] of Object.entries(p)) {
      if (JSON.stringify(v) === JSON.stringify((repo.stocks || {})[c] || null)) { delete p[c]; changed = true; }
    }
    if (changed) writePending(p);
    loaded = true;
    emit();
    if (token() && Object.keys(readPending()).length) sync().catch(() => {});
  }

  /* ---------- 保存 ---------- */
  let syncing = null;
  async function sync() {
    if (!token()) return false;
    if (syncing) return syncing;
    syncing = (async () => {
      for (let attempt = 0; attempt < 3; attempt++) {
        const p = readPending();
        const codes = Object.keys(p);
        if (!codes.length) return true;
        const { data, sha } = await apiGet();
        data.stocks = data.stocks || {};
        for (const c of codes) { if (p[c] === null) delete data.stocks[c]; else data.stocks[c] = p[c]; }
        data.updated = new Date().toISOString();
        const body = { message: "Update stock memo " + codes.join(",") + " (browser)",
          content: b64enc(JSON.stringify(data, null, 2) + "\n"), branch: "main" };
        if (sha) body.sha = sha;
        const r = await fetch("https://api.github.com/repos/" + REPO + "/contents/" + PATH, {
          method: "PUT", headers: { Authorization: "Bearer " + token(), Accept: "application/vnd.github+json" },
          body: JSON.stringify(body) });
        if (r.status === 409 || r.status === 422) continue;   // 他の更新と衝突 → 取り直して再試行
        if (!r.ok) throw new Error("GitHub API " + r.status + " " + (await r.text()).slice(0, 120));
        repo = data;
        // 送信中に増えた分は残す
        const now = readPending();
        for (const c of codes) if (JSON.stringify(now[c]) === JSON.stringify(p[c])) delete now[c];
        writePending(now);
        emit();
        return true;
      }
      throw new Error("衝突が続いたため保存できませんでした");
    })();
    try { return await syncing; } finally { syncing = null; }
  }

  function put(code, entry) {
    const p = readPending();
    p[code] = isEmpty(entry) ? null : entry;
    if (p[code] === null && !(repo.stocks || {})[code]) delete p[code];
    writePending(p);
    emit();
    return sync();
  }

  function emit() {
    for (const d of docs) refreshDots(d);
    for (const f of listeners) { try { f(); } catch (e) { console.error(e); } }
  }

  /* ---------- ● の差し込み ---------- */
  const docs = new Set();
  const CSS = `
.smemo-dot{display:inline-block;width:9px;height:9px;border-radius:50%;border:0;padding:0;margin:0 0 0 4px;
  vertical-align:middle;cursor:pointer;background:#5b8def;opacity:.55;flex:none;position:relative;top:-1px}
.smemo-dot:hover{opacity:1;transform:scale(1.25)}
.smemo-dot.has{background:#e5484d;opacity:1}
td.smemo-host{overflow:visible!important}
`;
  const nameLike = t => {
    t = (t || "").trim();
    if (!t || t.length > 40 || CODE_RE.test(t)) return false;
    if (/^[\d\s,.\-+%:\/()年月日円株億万倍]+$/.test(t)) return false;
    return /[A-Za-zＡ-Ｚａ-ｚ぀-ヿ一-鿿]/.test(t);
  };
  const ownText = el => (el ? el.textContent : "").replace(/\s+/g, " ").trim();

  function makeDot(doc, code, name) {
    const b = doc.createElement("button");
    b.type = "button";
    b.className = "smemo-dot" + (hasMemo(code) ? " has" : "");
    b.dataset.smemo = code;
    b.dataset.smemoName = name || "";
    b.title = (hasMemo(code) ? "メモあり" : "メモを書く") + "(" + code + ")";
    return b;
  }

  function decorate(doc) {
    const leaves = doc.querySelectorAll("td, th, span, a, b, strong, div, li");
    for (const el of leaves) {
      if (el.childElementCount) continue;
      const code = el.textContent.trim();
      if (code.length !== 4 || !CODE_RE.test(code)) continue;
      if (el.closest("thead, .smemo-skip, select, option, button, #smemo-modal")) continue;
      const cell = el.closest("td, th, li") || el;
      let target = null, mode = "append", name = "";
      if (ownText(cell) !== code && cell !== el) {
        // 名前とコードが同じセル(例: <a>キオクシア</a><br><span>285A</span>)
        const cand = [...cell.children].find(c => c !== el && !c.contains(el) && nameLike(ownText(c)));
        if (!cand) continue;
        target = cand; mode = "after"; name = ownText(cand);
      } else {
        const nx = cell.nextElementSibling, pv = cell.previousElementSibling;
        const pick = nameLike(ownText(nx)) ? nx : (nameLike(ownText(pv)) && pv && pv.tagName === cell.tagName ? pv : null);
        if (!pick) continue;
        target = pick; name = ownText(pick);
        mode = /^(TD|TH|LI)$/.test(pick.tagName) ? "append" : "after";
      }
      const holder = mode === "append" ? target : target.parentElement;
      if (!holder) continue;
      const existing = mode === "append" ? target.querySelector(":scope > .smemo-dot")
        : (target.nextElementSibling && target.nextElementSibling.classList.contains("smemo-dot") ? target.nextElementSibling : null);
      if (existing) { if (existing.dataset.smemo !== code) existing.dataset.smemo = code; continue; }
      const dot = makeDot(doc, code, name);
      if (mode === "append") { target.appendChild(dot); if (target.tagName === "TD") target.classList.add("smemo-host"); }
      else target.after(dot);
    }
  }

  function refreshDots(doc) {
    for (const b of doc.querySelectorAll(".smemo-dot")) {
      const h = hasMemo(b.dataset.smemo);
      b.classList.toggle("has", h);
      b.title = (h ? "メモあり" : "メモを書く") + "(" + b.dataset.smemo + ")";
    }
  }

  function attach(doc) {
    if (!doc || docs.has(doc) || !doc.body) return;
    docs.add(doc);
    const st = doc.createElement("style"); st.textContent = CSS; doc.head.appendChild(st);
    doc.addEventListener("click", ev => {
      const b = ev.target.closest && ev.target.closest(".smemo-dot");
      if (!b) return;
      ev.preventDefault(); ev.stopPropagation();
      open(b.dataset.smemo, b.dataset.smemoName);
    }, true);
    let timer = null;
    const run = () => { timer = null; try { decorate(doc); } catch (e) { console.error(e); } };
    new MutationObserver(muts => {
      if (muts.every(m => [...m.addedNodes].every(n => n.classList && n.classList.contains("smemo-dot")))) return;
      if (!timer) timer = setTimeout(run, 250);
    }).observe(doc.body, { childList: true, subtree: true, characterData: true });
    run();
    // 中の iframe にも差し込む
    const hook = f => {
      const go = () => { try { if (f.contentDocument && f.contentDocument.readyState !== "loading") attach(f.contentDocument); } catch (e) { /* 別オリジン */ } };
      if (f.dataset.smemoHooked) { go(); return; }
      f.dataset.smemoHooked = "1";
      f.addEventListener("load", () => { try { docs.delete(f.contentDocument); } catch (e) {} go(); });
      go();
    };
    doc.querySelectorAll("iframe").forEach(hook);
    new MutationObserver(() => doc.querySelectorAll("iframe:not([data-smemo-hooked])").forEach(hook))
      .observe(doc.body, { childList: true, subtree: true });
  }

  /* ---------- モーダル ---------- */
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const linkify = s => esc(s).replace(/https?:\/\/[^\s)）]+/g, u => '<a href="' + u + '" target="_blank" rel="noopener">' + u + "</a>");
  const today = () => { const d = new Date(); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); };
  const LIST_LABEL = { "": "なし", avoid: "不誠実・買う理由なし", buy: "不誠実だが、それをしのぐ買う理由あり" };

  let modal = null, cur = null;
  function ensureModal() {
    if (modal) return modal;
    const st = document.createElement("style");
    st.textContent = `
#smemo-modal{position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.45);display:flex;align-items:flex-start;justify-content:center;padding:6vh 12px;overflow:auto}
#smemo-modal[hidden]{display:none}
#smemo-modal a{color:#68d8d5}
#smemo-modal textarea,#smemo-modal input,#smemo-modal button{background:#152235;color:#e2ebf5;border:1px solid #3c5068;border-radius:6px}
#smemo-modal .box{background:#111d2c;color:#e2ebf5;border:1px solid #2c3c50;width:min(640px,100%);border-radius:10px;padding:16px 18px;box-shadow:0 10px 40px rgba(0,0,0,.3);font-size:14px;line-height:1.6}
#smemo-modal h3{margin:0 0 6px;font-size:17px}
#smemo-modal .sub{color:#888;font-size:12px}
#smemo-modal .lists{display:flex;flex-wrap:wrap;gap:6px 14px;margin:10px 0}
#smemo-modal .note{border-left:3px solid #e5484d;padding:4px 8px;margin:8px 0;background:rgba(127,127,127,.07);border-radius:0 6px 6px 0;white-space:pre-wrap;word-break:break-all}
#smemo-modal .note .meta{color:#888;font-size:12px;display:flex;gap:8px;align-items:center}
#smemo-modal .note .meta button{font-size:11px;padding:0 6px;cursor:pointer}
#smemo-modal textarea{width:100%;box-sizing:border-box;min-height:70px;font:inherit;padding:6px}
#smemo-modal .row{display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap}
#smemo-modal .row button{padding:4px 14px;cursor:pointer}
#smemo-modal .status{font-size:12px;color:#888}
#smemo-modal .status.warn{color:#c47a00}
#smemo-modal .status.err{color:#e5484d}
#smemo-modal details{margin-top:12px;font-size:12px;color:#888}
#smemo-modal details input{width:100%;box-sizing:border-box;font:inherit;padding:4px}
#smemo-modal .x{float:right;border:0!important;background:none!important;font-size:20px;cursor:pointer;color:#888}
`;
    document.head.appendChild(st);
    modal = document.createElement("div");
    modal.id = "smemo-modal"; modal.hidden = true;
    modal.innerHTML = '<div class="box"></div>';
    modal.addEventListener("click", e => { if (e.target === modal) close(); });
    document.addEventListener("keydown", e => { if (e.key === "Escape" && !modal.hidden) close(); });
    document.body.appendChild(modal);
    return modal;
  }
  function close() { if (modal) modal.hidden = true; cur = null; }

  function open(code, name) {
    ensureModal();
    cur = { code, name: name || (get(code) || {}).name || "" };
    render();
    modal.hidden = false;
    const ta = modal.querySelector("textarea.new"); if (ta) ta.focus();
  }

  function statusHTML(msg, cls) {
    const pend = readPending();
    if (msg) return '<span class="status ' + (cls || "") + '">' + esc(msg) + "</span>";
    if (!token()) return '<span class="status warn">この端末にだけ保存されます(GitHub連携が未設定)。</span>';
    if (pend[cur.code] !== undefined) return '<span class="status warn">未同期(送信待ち)</span>';
    return '<span class="status">GitHubに保存済み</span>';
  }

  function render(msg, cls) {
    if (!cur) return;
    const s = get(cur.code) || { name: cur.name, notes: [] };
    const name = s.name || cur.name;
    const notes = s.notes || [];
    const box = modal.querySelector(".box");
    box.innerHTML =
      '<button class="x" title="閉じる">×</button>' +
      "<h3>" + esc(name) + ' <span class="sub">' + esc(cur.code) + "</span></h3>" +
      '<div class="sub"><a href="https://kabutan.jp/stock/?code=' + encodeURIComponent(cur.code) + '" target="_blank" rel="noopener">株探で開く ↗</a></div>' +
      '<div class="lists">' + ["", "avoid", "buy"].map(k =>
        '<label><input type="radio" name="smemo-list" value="' + k + '"' + ((s.list || "") === k ? " checked" : "") + "> " + LIST_LABEL[k] + "</label>").join("") + "</div>" +
      '<div class="reasonbox"' + (s.list === "buy" ? "" : " hidden") + '><div class="sub">買う理由</div><textarea class="reason" placeholder="不誠実さをしのぐ買う理由">' + esc(s.reason || "") + "</textarea></div>" +
      (notes.length ? notes.map((n, i) =>
        '<div class="note"><div class="meta">' + esc(n.date || "") + " " + esc(n.by || "") +
        ' <button data-del="' + i + '">削除</button></div>' + linkify(n.text) +
        (n.src && n.src.length ? '<div class="sub">出典: ' + n.src.map(u => '<a href="' + esc(u) + '" target="_blank" rel="noopener">' + esc(u.replace(/^https?:\/\/(www\.)?/, "").slice(0, 40)) + "</a>").join(" / ") + "</div>" : "") +
        "</div>").join("") : '<div class="sub" style="margin:8px 0">メモはまだありません。</div>') +
      '<textarea class="new" placeholder="メモを追加(Ctrl+Enterで保存)"></textarea>' +
      '<div class="row"><button class="save">保存</button>' + statusHTML(msg, cls) + "</div>" +
      '<details><summary>GitHub連携(全端末・Claudeと共有する場合)</summary>' +
      "<p>トークンを入れると、メモは株ログのリポジトリ(公開)の data_memo/memos.json に直接保存され、他の端末やClaudeからも見えます。" +
      "fine-grained token で、対象リポジトリを kabulog だけ・権限を Contents: Read and write だけにしたものを推奨。トークンはこのブラウザの中にだけ保存されます。</p>" +
      '<input type="password" class="tok" placeholder="github_pat_..." value="' + (token() ? "********" : "") + '">' +
      '<div class="row"><button class="tsave">トークンを保存</button><button class="tclear">削除</button></div></details>';

    box.querySelector(".x").onclick = close;
    const reasonBox = box.querySelector(".reasonbox");
    box.querySelectorAll('input[name="smemo-list"]').forEach(r => r.onchange = () => { reasonBox.hidden = r.value !== "buy" || !r.checked; });
    box.querySelectorAll("[data-del]").forEach(b => b.onclick = () => {
      if (!confirm("このメモを削除しますか?")) return;
      const e = clone(s, name); e.notes.splice(+b.dataset.del, 1); save(e);
    });
    const doSave = () => {
      const e = clone(s, name);
      const sel = box.querySelector('input[name="smemo-list"]:checked');
      e.list = sel && sel.value ? sel.value : undefined;
      if (!e.list) delete e.list;
      const rs = box.querySelector("textarea.reason").value.trim();
      if (rs) e.reason = rs; else delete e.reason;
      const t = box.querySelector("textarea.new").value.trim();
      if (t) e.notes.push({ date: today(), by: "本人", text: t });
      save(e);
    };
    box.querySelector(".save").onclick = doSave;
    box.querySelector("textarea.new").onkeydown = e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) doSave(); };
    box.querySelector(".tsave").onclick = () => {
      const v = box.querySelector(".tok").value.trim();
      if (!v || v === "********") return;
      try { localStorage.setItem(LS_TOKEN, v); } catch (e) {}
      render("確認中…");
      load().then(() => sync()).then(() => render("トークンを保存しました。")).catch(err => render("トークンで読み書きできません: " + err.message, "err"));
    };
    box.querySelector(".tclear").onclick = () => { try { localStorage.removeItem(LS_TOKEN); } catch (e) {} render("トークンを削除しました。"); };
  }

  function clone(s, name) {
    const e = JSON.parse(JSON.stringify(s || {}));
    e.name = e.name || name || cur.name;
    e.notes = e.notes || [];
    return e;
  }
  function save(entry) {
    const code = cur.code;
    const p = put(code, entry);
    render(token() ? "保存中…" : null);
    Promise.resolve(p).then(() => { if (cur && cur.code === code) render(); })
      .catch(err => { if (cur && cur.code === code) render("GitHubへの保存に失敗(この端末には保存済み): " + err.message, "err"); });
  }

  window.StockMemo = {
    attach, open, get, stocks, hasMemo, put, sync, reload: load,
    lists: () => repo.lists || {},
    isLoaded: () => loaded,
    onChange: f => { listeners.push(f); if (loaded) f(); },
    pendingCount: () => Object.keys(readPending()).length,
    hasToken: () => !!token(),
  };
  const start = () => { attach(document); load(); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
