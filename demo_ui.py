"""
Local pipeline inspector UI (stdlib only).

  python demo_ui.py
  → http://127.0.0.1:8765
"""

from __future__ import annotations

import json
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from dotenv import load_dotenv

from semantic_layer.grounding.business_objects import load_business_objects
from semantic_layer.pipeline import Pipeline
from semantic_layer.execute import execute_sql, validate_sql

load_dotenv()

HOST = "127.0.0.1"
PORT = 8765
ROOT = Path(__file__).resolve().parent

_pipeline: Pipeline | None = None


def get_pipeline() -> Pipeline:
    global _pipeline
    if _pipeline is None:
        # Hybrid: rules first; Groq Intent fallback when GROQ_API_KEY is set
        _pipeline = Pipeline.from_kb(enable_llm_fallback=True)
    return _pipeline


def bo_options() -> list[str]:
    reg = load_business_objects()
    if reg is None:
        return ["Finance", "Logistics"]
    return sorted(reg.business_objects.keys())


def run_pipeline(question: str, bo_id: str | None) -> dict:
    full = get_pipeline().run_full(question, bo_id=bo_id or None)
    return full.model_dump(mode="json")


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Semantic Layer — Ask to SQL</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet" />
  <style>
    :root {
      --bg0: #0f1419;
      --bg1: #171e26;
      --bg2: #1e2833;
      --line: #2c3a4a;
      --text: #e8eef4;
      --muted: #8b9aab;
      --accent: #3d9a7a;
      --accent-dim: #2a6b55;
      --warn: #c9a227;
      --bad: #c45c5c;
      --ok: #3d9a7a;
      --chip: #243041;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "IBM Plex Sans", system-ui, sans-serif;
      color: var(--text);
      background:
        radial-gradient(1200px 600px at 10% -10%, #1a3d32 0%, transparent 55%),
        radial-gradient(900px 500px at 100% 0%, #1a2a40 0%, transparent 50%),
        var(--bg0);
    }
    .wrap {
      max-width: 1100px;
      margin: 0 auto;
      padding: 2rem 1.25rem 4rem;
    }
    header h1 {
      font-family: Fraunces, Georgia, serif;
      font-weight: 700;
      font-size: clamp(1.6rem, 3vw, 2.1rem);
      margin: 0 0 0.35rem;
      letter-spacing: -0.02em;
    }
    header p {
      margin: 0 0 1.75rem;
      color: var(--muted);
      max-width: 44rem;
      line-height: 1.45;
    }
    .panel {
      background: color-mix(in srgb, var(--bg1) 92%, transparent);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 1.25rem 1.35rem;
      margin-bottom: 1.25rem;
      backdrop-filter: blur(8px);
    }
    label {
      display: block;
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-bottom: 0.4rem;
    }
    textarea, select {
      width: 100%;
      font: inherit;
      color: var(--text);
      background: var(--bg2);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0.75rem 0.85rem;
    }
    textarea {
      min-height: 5.5rem;
      resize: vertical;
      line-height: 1.4;
    }
    textarea:focus, select:focus {
      outline: 2px solid var(--accent-dim);
      border-color: var(--accent);
    }
    .row {
      display: grid;
      grid-template-columns: 1fr 220px;
      gap: 1rem;
      margin-top: 1rem;
      align-items: end;
    }
    @media (max-width: 700px) {
      .row { grid-template-columns: 1fr; }
    }
    button.run {
      font: inherit;
      font-weight: 600;
      color: #04140f;
      background: var(--accent);
      border: none;
      border-radius: 8px;
      padding: 0.85rem 1.25rem;
      cursor: pointer;
      width: 100%;
    }
    button.run:hover { filter: brightness(1.08); }
    button.run:disabled {
      opacity: 0.55;
      cursor: wait;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.6rem;
      margin: 0.75rem 0 1rem;
    }
    button.secondary {
      font: inherit;
      font-weight: 600;
      color: var(--text);
      background: var(--bg2);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0.65rem 1rem;
      cursor: pointer;
    }
    button.secondary:hover { border-color: var(--accent); }
    button.secondary:disabled { opacity: 0.5; cursor: wait; }
    table.grid {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.82rem;
      margin-top: 0.75rem;
    }
    table.grid th, table.grid td {
      border: 1px solid var(--line);
      padding: 0.4rem 0.55rem;
      text-align: left;
      vertical-align: top;
    }
    table.grid th { background: var(--bg2); color: var(--muted); }
    .status-line {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-bottom: 1rem;
      min-height: 1.5rem;
    }
    .chip {
      font-size: 0.78rem;
      font-weight: 500;
      padding: 0.25rem 0.65rem;
      border-radius: 999px;
      background: var(--chip);
      border: 1px solid var(--line);
      color: var(--muted);
    }
    .chip.ok { color: #a8e6cf; border-color: var(--accent-dim); }
    .chip.bad { color: #f0b4b4; border-color: #6a3030; }
    .chip.warn { color: #f0e0a0; border-color: #6a5a20; }
    .section {
      border: 1px solid var(--line);
      border-radius: 10px;
      margin-bottom: 0.85rem;
      overflow: hidden;
      background: var(--bg1);
    }
    .section > summary {
      list-style: none;
      cursor: pointer;
      padding: 0.9rem 1.1rem;
      font-weight: 600;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
      user-select: none;
    }
    .section > summary::-webkit-details-marker { display: none; }
    .section > summary::after {
      content: "▾";
      color: var(--muted);
      font-size: 0.85rem;
    }
    .section:not([open]) > summary::after { content: "▸"; }
    .section .body {
      padding: 0 1.1rem 1.1rem;
      border-top: 1px solid var(--line);
    }
    .step-title {
      display: flex;
      align-items: baseline;
      gap: 0.55rem;
      flex-wrap: wrap;
    }
    .step-num {
      font-family: "IBM Plex Mono", ui-monospace, monospace;
      font-size: 0.85rem;
      font-weight: 500;
      color: var(--accent);
      letter-spacing: 0.02em;
    }
    .step-blurb {
      margin: 0.85rem 0 0.35rem;
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.45;
    }
    .io-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.85rem;
      margin: 0.75rem 0 0.35rem;
    }
    @media (max-width: 800px) {
      .io-grid { grid-template-columns: 1fr; }
    }
    .io-panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--bg0);
      padding: 0.75rem 0.9rem 0.9rem;
      min-width: 0;
    }
    .io-panel.out {
      border-color: color-mix(in srgb, var(--accent-dim) 70%, var(--line));
    }
    .io-label {
      font-size: 0.72rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      color: var(--muted);
      margin: 0 0 0.45rem;
    }
    .io-panel.out .io-label { color: #a8e6cf; }
    .io-panel .kv { margin: 0.35rem 0 0; }
    .io-panel pre {
      margin-top: 0.35rem;
      max-height: 260px;
    }
    .sql-block {
      margin: 0.75rem 0 0.35rem;
    }
    .sql-block pre {
      max-height: 280px;
      border-color: var(--accent-dim);
    }
    .tech {
      margin-top: 0.85rem;
      border: 1px dashed var(--line);
      border-radius: 8px;
      background: color-mix(in srgb, var(--bg0) 55%, var(--bg1));
    }
    .tech > summary {
      list-style: none;
      cursor: pointer;
      padding: 0.65rem 0.85rem;
      font-size: 0.82rem;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      user-select: none;
    }
    .tech > summary::-webkit-details-marker { display: none; }
    .tech > summary::after {
      content: " ▸";
      font-size: 0.75rem;
    }
    .tech[open] > summary::after { content: " ▾"; }
    .tech .tech-body {
      padding: 0 0.85rem 0.85rem;
    }
    .tech .tech-body label {
      margin-top: 0.65rem;
    }
    .kv {
      display: grid;
      gap: 0.55rem;
      margin: 0.85rem 0;
    }
    .kv div {
      display: grid;
      grid-template-columns: 12.5rem 1fr;
      gap: 0.75rem;
      font-size: 0.92rem;
    }
    @media (max-width: 600px) {
      .kv div { grid-template-columns: 1fr; gap: 0.15rem; }
    }
    .kv dt { color: var(--muted); margin: 0; }
    .kv dd { margin: 0; word-break: break-word; }
    pre {
      margin: 0.5rem 0 0;
      padding: 0.9rem 1rem;
      background: var(--bg0);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: auto;
      font-family: "IBM Plex Mono", ui-monospace, monospace;
      font-size: 0.78rem;
      line-height: 1.45;
      max-height: 420px;
    }
    .err {
      color: #f0b4b4;
      background: #2a1818;
      border: 1px solid #6a3030;
      border-radius: 8px;
      padding: 0.85rem 1rem;
      white-space: pre-wrap;
      font-family: "IBM Plex Mono", monospace;
      font-size: 0.8rem;
    }
    .empty { color: var(--muted); font-size: 0.95rem; }
    .hint { font-size: 0.8rem; color: var(--muted); margin-top: 0.6rem; }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>Ask → SQL walkthrough</h1>
      <p>Ask a question scoped to Finance or Logistics. We walk through cleaning → understanding → mapping → SQL → check → results — same pipeline data, shown step by step.</p>
    </header>

    <form class="panel" id="form">
      <label for="question">Question</label>
      <textarea id="question" name="question" required placeholder="show top 10 grds by revnue this yr">show top 10 grds by revnue this yr</textarea>
      <div class="row">
        <div>
          <label for="bo">Business object</label>
          <select id="bo" name="bo_id">__BO_OPTIONS__</select>
        </div>
        <button class="run" type="submit" id="runBtn">Run walkthrough</button>
      </div>
      <p class="hint"><b>Run walkthrough</b> fills steps 1–5 (check runs automatically). Click <b>Run SQL</b> for step 6 results from Postgres.</p>
      <div class="actions">
        <button class="secondary" type="button" id="validateBtn" disabled>Re-check SQL</button>
        <button class="secondary" type="button" id="executeBtn" disabled>Run SQL</button>
      </div>
    </form>

    <div class="status-line" id="status"></div>
    <div id="out"><p class="empty">Submit a question to see the walkthrough.</p></div>
  </div>

  <script>
    const form = document.getElementById("form");
    const out = document.getElementById("out");
    const status = document.getElementById("status");
    const runBtn = document.getElementById("runBtn");
    const validateBtn = document.getElementById("validateBtn");
    const executeBtn = document.getElementById("executeBtn");
    let lastOk = false;
    let lastSqlPreview = null;
    let progressState = {
      clean: null,
      intent: null,
      map: null,
      sql: null,
      check: null,
      results: null,
      bo: null,
      clauses: 0,
    };

    function chip(text, cls) {
      return `<span class="chip ${cls || ""}">${escapeHtml(text)}</span>`;
    }
    function escapeHtml(s) {
      return String(s)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }
    function pretty(obj) {
      return escapeHtml(JSON.stringify(obj, null, 2));
    }
    function statusClass(st) {
      if (!st || st === "—" || st === "null" || st === "?") return "";
      const u = String(st).toUpperCase();
      if (u === "VALID" || u === "OK" || u === "READY") return "ok";
      if (u === "PARTIAL" || u === "WAITING") return "warn";
      if (u === "FAILED" || u === "INVALID" || u === "ERROR") return "bad";
      return "";
    }
    function kv(rows) {
      const items = rows
        .filter(([, v]) => v !== undefined && v !== null && v !== "")
        .map(([k, v]) => {
          const val = typeof v === "object" ? `<code>${escapeHtml(JSON.stringify(v))}</code>` : escapeHtml(String(v));
          return `<div><dt>${escapeHtml(k)}</dt><dd>${val}</dd></div>`;
        })
        .join("");
      return `<div class="kv">${items}</div>`;
    }
    function techDetails(blocks) {
      if (!blocks || !blocks.length) return "";
      const inner = blocks
        .map(([label, content]) => `<label>${escapeHtml(label)}</label><pre>${content}</pre>`)
        .join("");
      return `<details class="tech"><summary>Technical details</summary><div class="tech-body">${inner}</div></details>`;
    }
    function ioPair(inputHtml, outputHtml) {
      return `<div class="io-grid">
        <div class="io-panel in"><p class="io-label">Input</p>${inputHtml}</div>
        <div class="io-panel out"><p class="io-label">Output</p>${outputHtml}</div>
      </div>`;
    }
    function preBlock(text) {
      return `<pre>${escapeHtml(text == null || text === "" ? "(none)" : String(text))}</pre>`;
    }
    function stepSection(num, title, badge, blurb, inner, open=true) {
      const badgeCls = statusClass(badge);
      return `<details class="section" ${open ? "open" : ""}>
        <summary>
          <span class="step-title"><span class="step-num">${escapeHtml(String(num))} ·</span><span>${escapeHtml(title)}</span></span>
          <span class="chip ${badgeCls}">${escapeHtml(badge)}</span>
        </summary>
        <div class="body">
          <p class="step-blurb">${escapeHtml(blurb)}</p>
          ${inner}
        </div>
      </details>`;
    }
    function clauseSuffix(i, total) {
      return total > 1 ? ` (clause ${i})` : "";
    }
    function renderProgress() {
      const p = progressState;
      const parts = [];
      if (p.bo !== null && p.bo !== undefined) {
        parts.push(chip(`BO: ${p.bo || "(unscoped)"}`));
      }
      if (p.clauses) parts.push(chip(`${p.clauses} clause(s)`));
      const steps = [
        ["1 Clean", p.clean],
        ["2 Intent", p.intent],
        ["3 Map", p.map],
        ["4 SQL", p.sql],
        ["5 Check", p.check],
        ["6 Results", p.results],
      ];
      steps.forEach(([label, st]) => {
        if (st === null || st === undefined) return;
        const text = st === "" || st === "—" ? label : `${label}: ${st}`;
        parts.push(chip(text, statusClass(st)));
      });
      status.innerHTML = parts.join("");
    }

    function render(data) {
      const n = data.normalized || {};
      const clauses = data.clauses || [];
      const boLabel = data.bo_id || "(unscoped)";

      progressState = {
        clean: n.normalized_question ? "ready" : "—",
        intent: (clauses[0] && clauses[0].intent && clauses[0].intent.status) || "—",
        map: (clauses[0] && clauses[0].grounded && clauses[0].grounded.status) || (clauses[0] && clauses[0].grounded === null ? "null" : "—"),
        sql: (clauses[0] && clauses[0].ir && clauses[0].ir.status) || "—",
        check: "…",
        results: "—",
        bo: boLabel,
        clauses: clauses.length,
      };
      renderProgress();

      lastSqlPreview = (clauses[0] && clauses[0].ir && clauses[0].ir.sql_preview) || null;

      let html = "";
      html += stepSection(
        1,
        "Clean the question",
        n.normalized_question ? "ready" : "—",
        "We fix typos and expand shorthand so matching is reliable.",
        ioPair(
          kv([["Original question", n.original_question]]),
          kv([
            ["Cleaned question", n.normalized_question],
            ["Text used for matching", n.matching_text],
            ["Unresolved words", (n.unresolved_tokens || []).join(", ") || "—"],
          ])
        ) + techDetails([["recognized_concepts", pretty(n.recognized_concepts || [])]])
      );

      clauses.forEach((cr, i) => {
        const intent = cr.intent || {};
        const g = cr.grounded;
        const ist = intent.status || "?";
        const gst = g ? (g.status || "?") : "null";
        const suf = clauseSuffix(i, clauses.length);
        const cleanedIn = n.matching_text || n.normalized_question || n.original_question || "(none)";

        html += stepSection(
          2,
          "Understand the intent" + suf,
          ist,
          "We parse what to measure, group, filter, and limit.",
          ioPair(
            kv([
              ["Cleaned question", cleanedIn],
              ["Business object", boLabel],
            ]),
            kv([
              ["Status", intent.status],
              ["Parser", intent.parser],
              ["Confidence", intent.confidence],
              ["Matched patterns", (intent.matched_patterns || []).join(", ") || "—"],
              ["Ambiguities", (intent.ambiguities || []).length ? intent.ambiguities : "—"],
              ["Errors", (intent.errors || []).length ? intent.errors : "—"],
            ])
          ) + techDetails([["intent_ast", pretty(intent.intent_ast)]])
        );

        if (!g) {
          html += stepSection(
            3,
            "Map to your data" + suf,
            "null",
            "We bind concepts to business-object tables, metrics, and joins.",
            ioPair(
              kv([
                ["Intent status", intent.status || "—"],
                ["Business object", boLabel],
              ]),
              `<p class="empty">No grounded context (missing intent AST or grounding disabled).</p>`
            )
          );
        } else {
          html += stepSection(
            3,
            "Map to your data" + suf,
            gst,
            "We bind concepts to business-object tables, metrics, and joins.",
            ioPair(
              kv([
                ["Intent status", intent.status || "—"],
                ["Business object", g.bo_id || boLabel],
                ["Matched patterns", (intent.matched_patterns || []).join(", ") || "—"],
              ]),
              kv([
                ["Status", g.status],
                ["Base entity", g.base_entity],
                ["Tables", (g.tables || []).join(", ") || "—"],
                ["Path IDs used", (g.applied_path_ids || []).join(", ") || "—"],
                ["Default filters", (g.default_filters || []).join(" | ") || "—"],
                ["Unresolved concepts", (g.unresolved_concepts || []).join(", ") || "—"],
                ["Errors", (g.errors || []).length ? g.errors : "—"],
              ])
            ) +
              techDetails([
                ["entities", pretty(g.entities || [])],
                ["metrics", pretty(g.metrics || [])],
                ["joins", pretty(g.joins || [])],
                ["time_filters", pretty(g.time_filters || [])],
                ["rules (top)", pretty((g.rules || []).slice(0, 5))],
                ["join_guidance (top)", pretty((g.join_guidance || []).slice(0, 5))],
              ])
          );
        }

        const ir = cr.ir;
        if (!ir) {
          html += stepSection(
            4,
            "Build the SQL" + suf,
            "null",
            "We compile a query plan, then the Postgres SQL that will run.",
            ioPair(
              kv([
                ["Grounding status", g ? g.status : "null"],
                ["Tables", g && g.tables ? g.tables.join(", ") : "—"],
              ]),
              `<p class="empty">No query plan yet.</p>`
            )
          );
        } else {
          html += stepSection(
            4,
            "Build the SQL" + suf,
            ir.status || "?",
            "We compile a query plan, then the Postgres SQL that will run.",
            ioPair(
              kv([
                ["Grounding status", g ? g.status : "null"],
                ["Base entity", g ? g.base_entity : "—"],
                ["Tables", g && g.tables ? g.tables.join(", ") : "—"],
                ["Metrics", g && g.metrics ? (g.metrics.length + " metric(s)") : "—"],
              ]),
              kv([
                ["Status", ir.status],
                ["Errors", (ir.errors || []).length ? ir.errors : "—"],
              ]) +
                `<div class="sql-block"><label>SQL to run</label>${preBlock(ir.sql_preview)}</div>`
            ) + techDetails([["query_ir", pretty(ir.ir)]])
          );
        }
      });

      html += `<div id="sqlExtras"><p class="empty">Steps 5–6 (check &amp; results) appear here…</p></div>`;
      html += stepSection(
        "·",
        "Full response (raw JSON)",
        "collapsed",
        "Complete API payload for debugging — same fields as above.",
        `<pre>${pretty(data)}</pre>`,
        false
      );
      out.innerHTML = html;

      lastOk = !!(clauses[0] && clauses[0].ir && clauses[0].ir.status === "VALID" && clauses[0].ir.sql_preview);
      validateBtn.disabled = !lastOk;
      executeBtn.disabled = !lastOk;
      if (lastOk) {
        autoValidate();
      } else {
        progressState.check = "skipped";
        renderProgress();
        const el = sqlExtrasEl();
        if (el) {
          el.innerHTML = stepSection(
            5,
            "Check the SQL",
            "skipped",
            "We verify the SQL is a single SELECT against allowed business-object tables.",
            ioPair(
              lastSqlPreview ? preBlock(lastSqlPreview) : `<p class="empty">No SQL yet.</p>`,
              `<p class="empty">Skipped — need a valid SQL preview first.</p>`
            )
          ) + `<div id="execSection"></div>`;
        }
      }
    }

    function sqlExtrasEl() {
      return document.getElementById("sqlExtras");
    }

    function payload() {
      return {
        question: document.getElementById("question").value,
        bo_id: document.getElementById("bo").value || null,
      };
    }

    async function postJson(url) {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload()),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || res.statusText);
      return data;
    }

    function renderValidation(v) {
      progressState.check = v.status || "?";
      renderProgress();
      const el = sqlExtrasEl();
      if (!el) return;
      const execSection = document.getElementById("execSection");
      const execHtml = execSection ? execSection.outerHTML : `<div id="execSection"></div>`;
      el.innerHTML =
        stepSection(
          5,
          "Check the SQL",
          v.status || "?",
          "We verify the SQL is a single SELECT against allowed business-object tables.",
          ioPair(
            `<label>SQL to check</label>${preBlock(lastSqlPreview)}`,
            kv([
              ["Status", v.status],
              ["Tables referenced", (v.tables_referenced || []).join(", ") || "—"],
              ["Errors", (v.errors || []).length ? v.errors : "—"],
              ["Warnings", (v.warnings || []).length ? v.warnings : "—"],
            ])
          ),
          true
        ) + execHtml;
    }

    function renderExecute(ex) {
      const ok = ex.status === "OK";
      progressState.results = ok ? `OK (${ex.row_count} rows)` : "FAILED";
      renderProgress();
      let outBody = kv([
        ["Status", ex.status],
        ["Row count", ex.row_count],
        ["Error", ex.error || "—"],
      ]);
      if (ex.validation) {
        outBody += kv([
          ["Validation", ex.validation.status],
          ["Validation errors", (ex.validation.errors || []).length ? ex.validation.errors : "—"],
        ]);
      }
      if (ok && ex.columns && ex.columns.length) {
        const head = ex.columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("");
        const rows = (ex.rows || []).map((r) =>
          `<tr>${r.map((c) => `<td>${escapeHtml(c === null || c === undefined ? "" : c)}</td>`).join("")}</tr>`
        ).join("");
        outBody += `<table class="grid"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>`;
      }
      const el = sqlExtrasEl();
      if (!el) return;
      const valOnly = el.querySelector("details.section");
      const valHtml = valOnly ? valOnly.outerHTML : "";
      const wrap = `<div id="execSection">${stepSection(
        6,
        "Run and see results",
        ex.status || "?",
        "We execute the checked SQL on Postgres and show the rows returned.",
        ioPair(
          `<label>SQL executed</label>${preBlock(lastSqlPreview)}`,
          outBody
        ),
        true
      )}</div>`;
      el.innerHTML = valHtml + wrap;
    }

    async function autoValidate() {
      const el = sqlExtrasEl();
      if (el) {
        el.innerHTML =
          stepSection(
            5,
            "Check the SQL",
            "…",
            "We verify the SQL is a single SELECT against allowed business-object tables.",
            ioPair(
              `<label>SQL to check</label>${preBlock(lastSqlPreview)}`,
              `<p class="empty">Checking SQL…</p>`
            )
          ) + `<div id="execSection"></div>`;
      }
      progressState.check = "…";
      renderProgress();
      try {
        const data = await postJson("/api/validate");
        renderValidation(data);
      } catch (err) {
        progressState.check = "ERROR";
        renderProgress();
        if (el) {
          el.innerHTML =
            stepSection(
              5,
              "Check the SQL",
              "ERROR",
              "We verify the SQL is a single SELECT against allowed business-object tables.",
              ioPair(
                `<label>SQL to check</label>${preBlock(lastSqlPreview)}`,
                `<div class="err">${escapeHtml(err.message || String(err))}</div>`
              )
            ) + `<div id="execSection"></div>`;
        }
      }
    }

    validateBtn.addEventListener("click", async () => {
      validateBtn.disabled = true;
      try {
        await autoValidate();
      } finally {
        validateBtn.disabled = !lastOk;
      }
    });

    executeBtn.addEventListener("click", async () => {
      executeBtn.disabled = true;
      const el = sqlExtrasEl();
      let execEl = document.getElementById("execSection");
      if (!execEl && el) {
        el.innerHTML += `<div id="execSection"></div>`;
        execEl = document.getElementById("execSection");
      }
      if (execEl) {
        execEl.innerHTML = stepSection(
          6,
          "Run and see results",
          "…",
          "We execute the checked SQL on Postgres and show the rows returned.",
          ioPair(
            `<label>SQL executed</label>${preBlock(lastSqlPreview)}`,
            `<p class="empty">Running SQL…</p>`
          )
        );
      }
      progressState.results = "…";
      renderProgress();
      try {
        const data = await postJson("/api/execute");
        renderExecute(data);
      } catch (err) {
        progressState.results = "ERROR";
        renderProgress();
        if (execEl) {
          execEl.innerHTML = stepSection(
            6,
            "Run and see results",
            "ERROR",
            "We execute the checked SQL on Postgres and show the rows returned.",
            ioPair(
              `<label>SQL executed</label>${preBlock(lastSqlPreview)}`,
              `<div class="err">${escapeHtml(err.message || String(err))}</div>`
            )
          );
        }
      } finally {
        executeBtn.disabled = !lastOk;
      }
    });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      runBtn.disabled = true;
      validateBtn.disabled = true;
      executeBtn.disabled = true;
      lastOk = false;
      lastSqlPreview = null;
      progressState = {
        clean: null, intent: null, map: null, sql: null, check: null, results: null,
        bo: null, clauses: 0,
      };
      status.innerHTML = chip("Running…");
      out.innerHTML = `<p class="empty">Working through the steps…</p>`;
      try {
        const res = await fetch("/api/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload()),
        });
        const data = await res.json();
        if (!res.ok) {
          status.innerHTML = chip("Error", "bad");
          out.innerHTML = `<div class="err">${escapeHtml(data.error || res.statusText)}</div>`;
          if (data.traceback) out.innerHTML += `<pre>${escapeHtml(data.traceback)}</pre>`;
          return;
        }
        render(data);
      } catch (err) {
        status.innerHTML = chip("Error", "bad");
        out.innerHTML = `<div class="err">${escapeHtml(err.message || String(err))}</div>`;
      } finally {
        runBtn.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


def _parse_payload(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(length) if length else b"{}"
    ctype = handler.headers.get("Content-Type") or ""
    if "application/json" in ctype:
        payload = json.loads(raw.decode("utf-8") or "{}")
    else:
        qs = parse_qs(raw.decode("utf-8"))
        payload = {
            "question": (qs.get("question") or [""])[0],
            "bo_id": (qs.get("bo_id") or [None])[0],
        }
    question = (payload.get("question") or "").strip()
    bo_id = payload.get("bo_id") or None
    if isinstance(bo_id, str) and not bo_id.strip():
        bo_id = None
    if not question:
        raise ValueError("question is required")
    return {"question": question, "bo_id": bo_id}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print(f"[demo_ui] {self.address_string()} - {fmt % args}")

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def do_GET(self) -> None:
        if self.path in {"/", "/index.html"}:
            options = "".join(
                f'<option value="{b}"' + (' selected' if b == "Finance" else "") + f">{b}</option>"
                for b in bo_options()
            )
            options += '<option value="">(unscoped)</option>'
            html = PAGE.replace("__BO_OPTIONS__", options)
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return
        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        try:
            if self.path == "/api/run":
                payload = _parse_payload(self)
                result = run_pipeline(payload["question"], payload["bo_id"])
                self._send_json(200, result)
                return

            if self.path == "/api/validate":
                payload = _parse_payload(self)
                full = get_pipeline().run_full(
                    payload["question"], bo_id=payload["bo_id"]
                )
                cr = full.clauses[0]
                sql = cr.ir.sql_preview if cr.ir else None
                v = validate_sql(
                    sql,
                    bo_id=payload["bo_id"],
                    grounded=cr.grounded,
                    ir_result=cr.ir,
                )
                self._send_json(200, v.model_dump(mode="json"))
                return

            if self.path == "/api/execute":
                payload = _parse_payload(self)
                full = get_pipeline().run_full(
                    payload["question"], bo_id=payload["bo_id"]
                )
                cr = full.clauses[0]
                sql = cr.ir.sql_preview if cr.ir else None
                if not sql:
                    raise ValueError("no sql_preview to execute")
                ex = execute_sql(
                    sql,
                    bo_id=payload["bo_id"],
                    grounded=cr.grounded,
                    ir_result=cr.ir,
                )
                self._send_json(200, ex.model_dump(mode="json"))
                return

            self._send(404, b"Not found", "text/plain; charset=utf-8")
        except Exception as exc:  # noqa: BLE001 — surface to UI
            self._send_json(
                500,
                {"error": str(exc), "traceback": traceback.format_exc()},
            )


def main() -> None:
    # Warm pipeline load so first click is faster
    print("Loading pipeline…", flush=True)
    get_pipeline()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Pipeline inspector: http://{HOST}:{PORT}", flush=True)
    print("Ctrl+C to stop", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
