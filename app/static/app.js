'use strict';

// Sovereign Hiring Console — Recruiter Console frontend.
// Vanilla JS, no framework, no build step, no CDN. Talks only to same-origin
// /api/* routes served by app/server.py.

const state = {
  job: null,
  candidates: [],
  biasCheck: null,
  auditLog: [],
};

// ---- tiny DOM helper -------------------------------------------------

function el(tag, opts = {}, children = []) {
  const node = document.createElement(tag);
  if (opts.className) node.className = opts.className;
  if (opts.text !== undefined) node.textContent = opts.text;
  if (opts.attrs) {
    for (const [key, value] of Object.entries(opts.attrs)) node.setAttribute(key, value);
  }
  children.forEach((child) => node.appendChild(child));
  return node;
}

function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

async function fetchJson(url, opts) {
  const res = await fetch(url, opts);
  let body = null;
  let parseFailed = false;
  try {
    body = await res.json();
  } catch (_err) {
    parseFailed = true;
  }
  if (!res.ok) {
    const message = (body && (body.error || body.message)) || res.statusText || 'Request failed';
    throw new Error(message);
  }
  if (parseFailed) {
    // A 200 with unparseable JSON is a real server-side bug, not "no data
    // yet" — throwing here (instead of silently returning null) keeps every
    // caller's existing error handling instead of letting this look like a
    // benign empty/loading state.
    throw new Error(`${url} returned a 200 response that was not valid JSON`);
  }
  return body;
}

// ---- pure helpers (covered by the self-test below) --------------------

function sortByScoreDesc(list) {
  return [...list].sort((a, b) => (b.score || 0) - (a.score || 0));
}

function isTopRank(zeroBasedIndex) {
  return zeroBasedIndex < 3;
}

const DECISION_VERB = { approve: 'approved', reject: 'rejected' };

function summarizeAuditEntry(entry) {
  const p = entry || {};
  if (p.event === 'ai_recommendation') {
    const parts = [];
    if (p.candidate_id) parts.push(`candidate ${p.candidate_id}`);
    if (p.score !== undefined) parts.push(`scored ${Number(p.score).toFixed(1)}`);
    if (p.rank !== undefined) parts.push(`rank #${p.rank}`);
    return parts.length ? `AI recommendation for ${parts.join(', ')}.` : 'AI produced a ranking recommendation.';
  }
  if (p.event === 'human_decision') {
    const actor = p.actor || 'someone';
    const verb = DECISION_VERB[p.decision] || p.decision || 'decided on';
    const candidate = p.candidate_id || 'a candidate';
    const reason = p.reason ? ` Reason given: "${p.reason}".` : '';
    return `${actor} ${verb} candidate ${candidate}.${reason}`;
  }
  return summarizeGenericPayload(p);
}

function summarizeGenericPayload(payload) {
  const skip = new Set(['ts', 'event']);
  const parts = Object.entries(payload)
    .filter(([key]) => !skip.has(key))
    .map(([key, value]) => `${key}: ${typeof value === 'object' ? JSON.stringify(value) : value}`);
  return parts.length ? parts.join(', ') : 'No further details.';
}

// ---- loaders ------------------------------------------------------------

async function loadJob() {
  state.job = await fetchJson('/api/job');
  renderJob();
}

async function loadBiasCheck() {
  state.biasCheck = await fetchJson('/api/bias-check');
  renderBiasCheck();
}

async function loadCandidates() {
  const data = await fetchJson('/api/candidates');
  // Server already sorts by score desc; sort again defensively so the UI
  // never trusts a single source for ranking (and top-3 stays correct).
  state.candidates = sortByScoreDesc(data);
  renderCandidates();
}

async function loadAuditLog() {
  state.auditLog = await fetchJson('/api/audit-log');
  renderAuditLog();
}

// ---- rendering: header / bias check --------------------------------------

function renderJob() {
  const job = state.job || {};
  document.getElementById('job-title').textContent = job.title || 'Untitled role';
  document.getElementById('job-location').textContent = job.location || '';
}

function renderBiasCheck() {
  const container = document.getElementById('bias-check-content');
  clear(container);
  const bc = state.biasCheck;
  if (!bc || !bc.groups || Object.keys(bc.groups).length === 0) {
    container.appendChild(el('p', { className: 'muted', text: 'No bias-check data available.' }));
    return;
  }

  const table = el('table', { className: 'bias-table' });
  const headRow = el('tr', {}, [
    el('th', { text: 'Group' }),
    el('th', { text: 'N' }),
    el('th', { text: 'Avg score' }),
  ]);
  table.appendChild(el('thead', {}, [headRow]));

  const tbody = el('tbody');
  Object.entries(bc.groups).forEach(([name, stats]) => {
    tbody.appendChild(el('tr', {}, [
      el('td', { text: name }),
      el('td', { text: String(stats.n) }),
      el('td', { text: stats.avg_score === null ? '— (withheld, n<3)' : Number(stats.avg_score).toFixed(1) }),
    ]));
  });
  table.appendChild(tbody);
  container.appendChild(table);

  if (bc.max_spread !== undefined) {
    container.appendChild(el('p', {
      className: 'max-spread',
      text: `Max spread between groups: ${Number(bc.max_spread).toFixed(1)} points`,
    }));
  }
  if (bc.statement) {
    container.appendChild(el('p', { className: 'bias-statement', text: bc.statement }));
  }
}

// ---- rendering: candidate cards -------------------------------------------

function statusLabel(status) {
  return { pending: 'Pending', approved: 'Approved', rejected: 'Rejected' }[status] || status || 'Pending';
}

function renderCandidates() {
  const container = document.getElementById('candidate-list');
  clear(container);
  if (state.candidates.length === 0) {
    container.appendChild(el('p', { className: 'muted', text: 'No candidates found.' }));
    return;
  }
  state.candidates.forEach((cand, index) => container.appendChild(renderCandidateCard(cand, index)));
}

function renderSkillGroup(label, items, tagClass) {
  const wrap = el('div', { className: 'skill-group' });
  wrap.appendChild(el('strong', { text: `${label}: ` }));
  if (!items || items.length === 0) {
    wrap.appendChild(el('span', { className: 'muted', text: 'none' }));
    return wrap;
  }
  items.forEach((item) => wrap.appendChild(el('span', { className: `tag ${tagClass}`, text: item })));
  return wrap;
}

function renderRedactedDetails(cand) {
  const details = el('details', { className: 'redacted-fields' });
  details.appendChild(el('summary', { text: 'Redacted fields' }));

  const removed = cand.removed_fields || [];
  details.appendChild(el('p', {
    text: removed.length ? `Removed entirely: ${removed.join(', ')}` : 'No fields removed entirely.',
  }));

  const spans = cand.scrubbed_spans || [];
  if (spans.length === 0) {
    details.appendChild(el('p', { text: 'No free-text spans scrubbed.' }));
    return details;
  }
  const list = el('ul', { className: 'scrub-list' });
  spans.forEach((span) => {
    list.appendChild(el('li', {}, [
      el('span', { className: 'field', text: `${span.field}: ` }),
      el('span', { className: 'original', text: `"${span.original}"` }),
      el('span', { className: 'arrow', text: ' → ' }),
      el('span', { className: 'redacted', text: span.replacement || '[REDACTED]' }),
    ]));
  });
  details.appendChild(list);
  return details;
}

function renderDecisionMeta(cand) {
  const who = cand.decision_actor || 'unknown';
  const reason = cand.decision_reason ? ` — reason: "${cand.decision_reason}"` : '';
  return el('p', {
    className: 'decision-meta',
    text: `${statusLabel(cand.decision_status)} by ${who}${reason}`,
  });
}

function renderDecisionArea(cand, rank) {
  const area = el('div', { className: 'decision-area' });
  const approveBtn = el('button', {
    className: 'btn approve-btn', text: 'Approve',
    attrs: { type: 'button', 'aria-label': `Approve candidate ${cand.id}` },
  });
  const rejectBtn = el('button', {
    className: 'btn reject-btn', text: 'Reject',
    attrs: { type: 'button', 'aria-label': `Reject candidate ${cand.id}` },
  });

  const reasonBox = el('div', { className: 'reason-box' });
  reasonBox.hidden = true;
  const reasonInputId = `reason-input-${cand.id}`;
  const label = el('label', {
    text: 'Reason for overriding a top-3 candidate (required):',
    attrs: { for: reasonInputId },
  });
  const textarea = el('textarea', {
    className: 'reason-input',
    attrs: { rows: '2', id: reasonInputId },
  });
  const confirmBtn = el('button', {
    className: 'btn confirm-reject-btn', text: 'Confirm reject',
    attrs: { type: 'button', 'aria-label': `Confirm reject for candidate ${cand.id}` },
  });
  const cancelBtn = el('button', {
    className: 'btn cancel-btn', text: 'Cancel',
    attrs: { type: 'button', 'aria-label': `Cancel reject for candidate ${cand.id}` },
  });
  reasonBox.appendChild(label);
  reasonBox.appendChild(textarea);
  reasonBox.appendChild(el('div', { className: 'reason-actions' }, [confirmBtn, cancelBtn]));

  approveBtn.addEventListener('click', () => submitDecision(cand.id, 'approve'));

  rejectBtn.addEventListener('click', () => {
    if (isTopRank(rank - 1)) {
      reasonBox.hidden = false;
      textarea.focus();
    } else {
      submitDecision(cand.id, 'reject');
    }
  });

  confirmBtn.addEventListener('click', () => {
    const reason = textarea.value.trim();
    if (!reason) {
      alert('A written reason is required to reject a top-3-ranked candidate.');
      return;
    }
    submitDecision(cand.id, 'reject', reason);
  });

  cancelBtn.addEventListener('click', () => {
    reasonBox.hidden = true;
    textarea.value = '';
  });

  area.appendChild(approveBtn);
  area.appendChild(rejectBtn);
  area.appendChild(reasonBox);
  return area;
}

function renderCandidateCard(cand, index) {
  const rank = index + 1;
  const card = el('article', { className: 'card', attrs: { 'data-id': cand.id } });

  card.appendChild(el('div', { className: 'card-header' }, [
    el('span', { className: 'rank', text: `#${rank}` }),
    el('span', { className: 'cand-id', text: cand.id }),
    el('span', { className: 'score', text: `${Number(cand.score).toFixed(1)} pts` }),
    el('span', { className: `status status-${cand.decision_status || 'pending'}`, text: statusLabel(cand.decision_status) }),
  ]));

  card.appendChild(el('p', { className: 'explanation', text: cand.explanation || '' }));

  card.appendChild(renderSkillGroup('Matched must-haves', cand.matched_must_haves, 'tag-good'));
  card.appendChild(renderSkillGroup('Missing must-haves', cand.missing_must_haves, 'tag-bad'));
  card.appendChild(renderSkillGroup('Matched nice-to-haves', cand.matched_nice_to_haves, 'tag-nice'));

  card.appendChild(renderRedactedDetails(cand));
  card.appendChild(renderDecisionArea(cand, rank));

  if (cand.decision_status && cand.decision_status !== 'pending') {
    card.appendChild(renderDecisionMeta(cand));
  }

  return card;
}

// ---- decisions -------------------------------------------------------

function askActorName() {
  const actor = window.prompt('Your name, for the audit log:');
  if (actor === null) return null;
  const trimmed = actor.trim();
  return trimmed.length ? trimmed : null;
}

async function submitDecision(candidateId, decision, reason) {
  const actor = askActorName();
  if (!actor) {
    alert('An actor name is required to record a decision.');
    return;
  }
  const body = { candidate_id: candidateId, decision, actor };
  if (reason) body.reason = reason;
  try {
    await fetchJson('/api/decide', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch (err) {
    alert(`Could not record decision: ${err.message}`);
    return;
  }
  // The decision itself is already saved at this point — a failure here is
  // only a stale view, not a lost decision, so it must not be reported with
  // the same "could not record decision" message (which would wrongly
  // invite the recruiter to resubmit and double-log the same decision).
  try {
    await Promise.all([loadCandidates(), loadAuditLog()]);
  } catch (err) {
    alert(`Decision recorded, but the view failed to refresh (${err.message}). Reload the page to see it.`);
  }
}

// ---- rendering: audit log ----------------------------------------------

function renderAuditEntry(entry) {
  const item = el('li', { className: 'audit-entry' });
  item.appendChild(el('span', { className: 'audit-ts', text: entry.ts || '' }));
  item.appendChild(el('span', { className: `audit-event event-${entry.event || 'unknown'}`, text: entry.event || 'event' }));
  item.appendChild(el('span', { className: 'audit-summary', text: summarizeAuditEntry(entry) }));
  return item;
}

function renderAuditLog() {
  const container = document.getElementById('audit-log');
  clear(container);
  if (state.auditLog.length === 0) {
    container.appendChild(el('p', { className: 'muted', text: 'No audit events yet.' }));
    return;
  }
  // Defensive: render newest first even if the feed order ever changes.
  const entries = [...state.auditLog].sort((a, b) => (b.ts || '').localeCompare(a.ts || ''));
  const list = el('ol', { className: 'audit-timeline' });
  entries.forEach((entry) => list.appendChild(renderAuditEntry(entry)));
  container.appendChild(list);
}

// ---- tabs & init -------------------------------------------------------

function setupTabs() {
  const buttons = Array.from(document.querySelectorAll('.tab-btn'));
  buttons.forEach((btn) => {
    btn.addEventListener('click', () => {
      buttons.forEach((b) => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
    });
  });
}

async function init() {
  setupTabs();
  try {
    await Promise.all([loadJob(), loadBiasCheck(), loadCandidates(), loadAuditLog()]);
  } catch (err) {
    console.error('Failed to load console data', err);
    document.body.insertBefore(
      el('p', { className: 'error-banner', text: `Failed to load data: ${err.message}` }),
      document.body.firstChild,
    );
  }
}

// ---- self-test (run with ?selftest in the URL; no test framework needed) --

function runSelfTest() {
  console.assert(isTopRank(0) === true, 'rank 1 (index 0) should be top-3');
  console.assert(isTopRank(2) === true, 'rank 3 (index 2) should be top-3');
  console.assert(isTopRank(3) === false, 'rank 4 (index 3) should not be top-3');

  const sorted = sortByScoreDesc([{ score: 10 }, { score: 90 }, { score: 50 }]);
  console.assert(sorted[0].score === 90 && sorted[2].score === 10, 'sortByScoreDesc must sort descending');

  const rejectSummary = summarizeAuditEntry({
    event: 'human_decision', actor: 'Ada', decision: 'reject', candidate_id: 'cand-01', reason: 'x',
  });
  console.assert(rejectSummary.startsWith('Ada rejected candidate cand-01.'), `reject verb should conjugate correctly, got: ${rejectSummary}`);

  const approveSummary = summarizeAuditEntry({
    event: 'human_decision', actor: 'Ada', decision: 'approve', candidate_id: 'cand-02',
  });
  console.assert(approveSummary.startsWith('Ada approved candidate cand-02.'), `approve verb should conjugate correctly, got: ${approveSummary}`);

  console.log('app.js self-test passed');
}

document.addEventListener('DOMContentLoaded', () => {
  init();
  if (window.location.search.includes('selftest')) runSelfTest();
});
