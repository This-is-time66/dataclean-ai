// ════════════════════════════════════════════
//  CONFIG — change this to your backend URL
// ════════════════════════════════════════════
const API = '';

// ════════════════════════════════════════════
//  STATE
// ════════════════════════════════════════════
let authToken        = localStorage.getItem('dc_token') || null;
let authUser         = JSON.parse(localStorage.getItem('dc_user') || 'null');
let selectedFile     = null;
let currentData      = null;
let tableRows        = [];
let currentPage      = 1;
const PAGE_SIZE      = 20;
let isViewingHistory = false;
let historyCount     = 0;

// ════════════════════════════════════════════
//  TOAST
// ════════════════════════════════════════════
function showToast(msg, duration = 2500) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), duration);
}

// ════════════════════════════════════════════
//  CLEAR PAGE CONTENT
// ════════════════════════════════════════════
function clearPageContent() {
  selectedFile     = null;
  currentData      = null;
  isViewingHistory = false;
  if (document.getElementById('file-input')) document.getElementById('file-input').value = '';
  document.getElementById('file-selected').classList.remove('show');
  document.getElementById('btn-analyze').disabled = true;
  document.getElementById('btn-analyze').innerHTML = `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M4.93 4.93a10 10 0 0 0 0 14.14"/></svg>Analyse with AI Agent`;
  document.getElementById('results').classList.remove('show');
  document.getElementById('progress-wrap').classList.remove('show');
  document.getElementById('history-viewing-banner').style.display = 'none';
  stepKeys.forEach(k => steps[k].className = 'pipe-step');
  document.querySelectorAll('.history-item').forEach(e => e.classList.remove('active'));
  hideError();
}

// ════════════════════════════════════════════
//  NAV RENDER
// ════════════════════════════════════════════
function renderNav() {
  const navRight = document.getElementById('nav-right');
  if (authUser) {
    const initials = authUser.full_name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0,2);
    navRight.innerHTML = `
      <button class="btn-nav btn-history" onclick="toggleSidebar()" id="btn-hist-toggle">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
        History
      </button>
      <button class="btn-profile" onclick="openProfile()">
        <div class="avatar">${initials}</div>
        ${authUser.full_name.split(' ')[0]}
      </button>
    `;
  } else {
    navRight.innerHTML = `
      <button class="btn-nav btn-nav-outline" onclick="openAuth('login')">Sign In</button>
      <button class="btn-nav btn-nav-solid"   onclick="openAuth('signup')">Sign Up</button>
    `;
  }
}

// ════════════════════════════════════════════
//  AUTH MODAL
// ════════════════════════════════════════════
function openAuth(tab = 'login') {
  document.getElementById('auth-overlay').classList.add('show');
  switchTab(tab);
  clearAuthError();
}
function closeAuth() { document.getElementById('auth-overlay').classList.remove('show'); }
document.getElementById('auth-close').onclick = closeAuth;
document.getElementById('auth-overlay').addEventListener('click', e => {
  if (e.target === document.getElementById('auth-overlay')) closeAuth();
});

function switchTab(tab) {
  document.getElementById('tab-login').classList.toggle('active',  tab==='login');
  document.getElementById('tab-signup').classList.toggle('active', tab==='signup');
  document.getElementById('form-login').style.display  = tab==='login'  ? '' : 'none';
  document.getElementById('form-signup').style.display = tab==='signup' ? '' : 'none';
  clearAuthError();
}

function showAuthError(msg) { const el = document.getElementById('auth-error'); el.textContent = msg; el.classList.add('show'); }
function clearAuthError()   { const el = document.getElementById('auth-error'); el.textContent = ''; el.classList.remove('show'); }

async function doLogin() {
  const email    = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;
  if (!email || !password) { showAuthError('Please fill in all fields.'); return; }

  const btn = document.getElementById('btn-login-submit');
  btn.disabled = true; btn.textContent = 'Signing in…';

  try {
    const res  = await fetch(`${API}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    if (!res.ok) { showAuthError(data.detail || 'Login failed.'); return; }
    saveAuth(data);
    closeAuth();
    loadHistory();
    showToast(`👋 Welcome back, ${data.full_name.split(' ')[0]}!`);
  } catch { showAuthError('Cannot reach backend.'); }
  finally { btn.disabled = false; btn.textContent = 'Sign In'; }
}

async function doSignup() {
  const full_name = document.getElementById('signup-name').value.trim();
  const email     = document.getElementById('signup-email').value.trim();
  const password  = document.getElementById('signup-password').value;
  if (!full_name || !email || !password) { showAuthError('Please fill in all fields.'); return; }

  const btn = document.getElementById('btn-signup-submit');
  btn.disabled = true; btn.textContent = 'Creating account…';

  try {
    const res  = await fetch(`${API}/auth/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, full_name }),
    });
    const data = await res.json();
    if (!res.ok) { showAuthError(data.detail || 'Signup failed.'); return; }
    saveAuth(data);
    closeAuth();
    loadHistory();
    showToast(`✅ Account created! Welcome, ${data.full_name.split(' ')[0]}!`);
  } catch { showAuthError('Cannot reach backend.'); }
  finally { btn.disabled = false; btn.textContent = 'Create Account'; }
}

document.getElementById('btn-login-submit').onclick  = doLogin;
document.getElementById('btn-signup-submit').onclick = doSignup;
['login-email','login-password','signup-name','signup-email','signup-password'].forEach(id => {
  document.getElementById(id).addEventListener('keydown', e => {
    if (e.key === 'Enter') { id.startsWith('login') ? doLogin() : doSignup(); }
  });
});

function saveAuth(data) {
  clearPageContent();
  document.getElementById('sidebar').classList.remove('show');
  authToken = data.token;
  authUser  = { email: data.email, full_name: data.full_name, user_id: data.user_id };
  localStorage.setItem('dc_token', authToken);
  localStorage.setItem('dc_user', JSON.stringify(authUser));
  renderNav();
}

function logout() {
  clearPageContent();
  authToken = null; authUser = null;
  localStorage.removeItem('dc_token');
  localStorage.removeItem('dc_user');
  renderNav();
  document.getElementById('sidebar').classList.remove('show');
  document.getElementById('history-list').innerHTML = EMPTY_HISTORY_HTML;
  document.getElementById('sidebar-count').textContent = '0 saved analyses';
  showToast('You have been signed out.');
}

// ════════════════════════════════════════════
//  PROFILE MODAL
// ════════════════════════════════════════════
function openProfile() {
  if (!authUser) return;
  const initials = authUser.full_name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0,2);
  document.getElementById('profile-avatar-large').textContent = initials;
  document.getElementById('profile-name-display').textContent = authUser.full_name;
  document.getElementById('profile-email-display').textContent = authUser.email;
  document.getElementById('pi-name').textContent  = authUser.full_name;
  document.getElementById('pi-email').textContent = authUser.email;
  document.getElementById('pi-count').textContent = historyCount + ' saved';
  document.getElementById('pi-since').textContent = '–';
  document.getElementById('delete-confirm-box').classList.remove('show');

  if (authToken) {
    fetch(`${API}/auth/me`, { headers: { 'Authorization': `Bearer ${authToken}` } })
      .then(r => r.json())
      .then(d => {
        if (d.created_at) {
          document.getElementById('pi-since').textContent =
            new Date(d.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
        }
      }).catch(() => {});
  }

  document.getElementById('profile-overlay').classList.add('show');
}

function closeProfile() {
  document.getElementById('profile-overlay').classList.remove('show');
  document.getElementById('delete-confirm-box').classList.remove('show');
  const btn = document.getElementById('btn-del-confirm-yes');
  btn.textContent = 'Yes, Delete';
  btn.disabled = false;
}

document.getElementById('profile-close').onclick = closeProfile;
document.getElementById('profile-overlay').addEventListener('click', e => {
  if (e.target === document.getElementById('profile-overlay')) closeProfile();
});

function logoutFromProfile() {
  closeProfile();
  logout();
}

function toggleDeleteConfirm() {
  document.getElementById('delete-confirm-box').classList.toggle('show');
}

async function deleteAccount() {
  const btn = document.getElementById('btn-del-confirm-yes');
  btn.textContent = 'Deleting…';
  btn.disabled = true;

  try {
    const res = await fetch(`${API}/auth/account`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${authToken}` },
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `Server error ${res.status}`);
    }
    closeProfile();
    logout();
    showToast('✅ Your account and all data have been permanently deleted.');
  } catch (e) {
    btn.textContent = 'Yes, Delete';
    btn.disabled = false;
    showToast('❌ Failed to delete: ' + e.message);
  }
}

// ════════════════════════════════════════════
//  HISTORY SIDEBAR
// ════════════════════════════════════════════
const EMPTY_HISTORY_HTML = `<div class="sidebar-empty"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>No analyses yet</div>`;

function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('show');
}

function closeSidebar() {
  document.getElementById('sidebar').classList.remove('show');
}

async function loadHistory() {
  if (!authToken) return;
  try {
    const res  = await fetch(`${API}/history`, { headers: { 'Authorization': `Bearer ${authToken}` } });
    if (!res.ok) return;
    const data = await res.json();
    historyCount = data.length;
    renderHistoryList(data);
  } catch {}
}

function renderHistoryList(items) {
  const list  = document.getElementById('history-list');
  const count = document.getElementById('sidebar-count');
  historyCount = items.length;
  count.textContent = `${items.length} saved analyse${items.length !== 1 ? 's' : ''}`;

  if (!items.length) {
    list.innerHTML = EMPTY_HISTORY_HTML;
    return;
  }

  list.innerHTML = items.map(item => {
    const date = new Date(item.created_at).toLocaleDateString('en-GB', { day:'numeric', month:'short', year:'numeric' });
    return `
      <div class="history-item" data-id="${item.id}" onclick="loadHistoryItem('${item.id}', this)">
        <div class="hi-name">${escHtml(item.file_name)}<button class="hi-del" onclick="deleteHistoryItem(event,'${item.id}')">✕</button></div>
        <div class="hi-meta">${item.original_rows} rows → ${item.cleaned_rows} rows &nbsp;·&nbsp; ${date}</div>
      </div>`;
  }).join('');
}

async function loadHistoryItem(id, el) {
  document.querySelectorAll('.history-item').forEach(e => e.classList.remove('active'));
  el.classList.add('active');

  try {
    const res  = await fetch(`${API}/history/${id}`, { headers: { 'Authorization': `Bearer ${authToken}` } });
    if (!res.ok) { showError('Could not load analysis.'); return; }
    const data = await res.json();

    isViewingHistory = true;
    currentData = {
      status:          'success',
      original_shape:  { rows: data.original_rows, columns: data.original_cols },
      cleaned_shape:   { rows: data.cleaned_rows,  columns: data.cleaned_cols  },
      eda_report:      typeof data.eda_report === 'string' ? JSON.parse(data.eda_report) : data.eda_report,
      logs:            typeof data.logs === 'string' ? JSON.parse(data.logs) : data.logs,
      summary:         data.summary,
      cleaned_columns: typeof data.cleaned_columns === 'string' ? JSON.parse(data.cleaned_columns) : data.cleaned_columns,
      cleaned_data:    typeof data.cleaned_data === 'string' ? JSON.parse(data.cleaned_data) : data.cleaned_data,
    };

    document.getElementById('history-viewing-banner').style.display = '';
    renderResults(currentData);
  } catch (e) { showError('Failed to load: ' + e.message); }
}

async function deleteHistoryItem(e, id) {
  e.stopPropagation();
  if (!confirm('Delete this analysis?')) return;
  try {
    await fetch(`${API}/history/${id}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${authToken}` },
    });
    loadHistory();
    document.getElementById('results').classList.remove('show');
  } catch {}
}

// ════════════════════════════════════════════
//  FILE HANDLING
// ════════════════════════════════════════════
function fmt(bytes) {
  return bytes < 1024 ? bytes + ' B' : bytes < 1048576 ? (bytes/1024).toFixed(1) + ' KB' : (bytes/1048576).toFixed(2) + ' MB';
}
function setFile(f) {
  if (!f) return;
  hideError();
  if (!f.name.toLowerCase().endsWith('.csv')) { showError('Only .csv files are accepted.'); return; }
  if (f.size > 1048576) { showError('File exceeds the 1 MB limit.'); return; }
  if (f.size === 0) { showError('The selected file is empty.'); return; }
  selectedFile = f;
  document.getElementById('file-name').textContent = f.name;
  document.getElementById('file-size').textContent = fmt(f.size);
  document.getElementById('file-selected').classList.add('show');
  document.getElementById('btn-analyze').disabled = false;
}

const dropZone  = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
dropZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', e => setFile(e.target.files[0]));
dropZone.addEventListener('dragover',  e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', ()  => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => { e.preventDefault(); dropZone.classList.remove('drag-over'); setFile(e.dataTransfer.files[0]); });
document.getElementById('file-remove').addEventListener('click', () => {
  selectedFile = null; fileInput.value = '';
  document.getElementById('file-selected').classList.remove('show');
  document.getElementById('btn-analyze').disabled = true;
  hideError();
});

function showError(msg) { document.getElementById('error-msg').textContent = msg; document.getElementById('error-box').classList.add('show'); }
function hideError()    { document.getElementById('error-box').classList.remove('show'); }

// ════════════════════════════════════════════
//  PIPELINE ANIMATION
// ════════════════════════════════════════════
const stepKeys   = ['eda','plan','clean','encode','story'];
const stepLabels = ['Running EDA…','AI planning strategy…','Cleaning data…','Encoding features…','Generating summary…'];
let stepTimer;
const steps = {
  eda:    document.getElementById('step-eda'),
  plan:   document.getElementById('step-plan'),
  clean:  document.getElementById('step-clean'),
  encode: document.getElementById('step-encode'),
  story:  document.getElementById('step-story'),
};

function animateSteps() {
  let i = 0;
  function next() {
    if (i > 0) steps[stepKeys[i-1]].className = 'pipe-step done';
    if (i < stepKeys.length) {
      steps[stepKeys[i]].className = 'pipe-step active';
      document.getElementById('progress-log').textContent = stepLabels[i];
      i++;
      stepTimer = setTimeout(next, 1800);
    } else {
      document.getElementById('progress-log').textContent = 'Finalising…';
    }
  }
  next();
}
function markAllDone() {
  stepKeys.forEach(k => steps[k].className = 'pipe-step done');
  document.getElementById('progress-log').textContent = 'Analysis complete ✓';
}

// ════════════════════════════════════════════
//  ANALYSE
// ════════════════════════════════════════════
document.getElementById('btn-analyze').addEventListener('click', async () => {
  if (!selectedFile) return;
  hideError();
  isViewingHistory = false;
  document.getElementById('results').classList.remove('show');
  document.getElementById('history-viewing-banner').style.display = 'none';
  document.getElementById('progress-wrap').classList.add('show');
  document.getElementById('btn-analyze').disabled = true;
  document.getElementById('btn-analyze').innerHTML = '<span class="spinner"></span> Analysing…';
  stepKeys.forEach(k => steps[k].className = 'pipe-step');
  animateSteps();

  const fd = new FormData();
  fd.append('file', selectedFile);
  const headers = {};
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

  try {
    const res = await fetch(`${API}/analyze`, { method: 'POST', body: fd, headers });
    let data;
    try { data = await res.json(); } catch { data = null; }
    if (!res.ok) throw new Error(data?.detail || `Server returned ${res.status}`);
    clearTimeout(stepTimer);
    markAllDone();
    currentData = data;
    document.querySelectorAll('.history-item').forEach(e => e.classList.remove('active'));
    setTimeout(() => {
      renderResults(data);
      if (authToken) loadHistory();
    }, 600);
  } catch (err) {
    clearTimeout(stepTimer);
    document.getElementById('progress-wrap').classList.remove('show');
    stepKeys.forEach(k => steps[k].className = 'pipe-step');
    let msg = err.message;
    if (msg.includes('Failed to fetch') || msg.includes('NetworkError'))
      msg = 'Cannot reach the backend. Make sure the server is running: uvicorn app:app --reload';
    showError(msg);
  } finally {
    document.getElementById('btn-analyze').disabled = false;
    document.getElementById('btn-analyze').innerHTML = `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M4.93 4.93a10 10 0 0 0 0 14.14"/></svg>Analyse with AI Agent`;
  }
});

// ════════════════════════════════════════════
//  RENDER RESULTS
// ════════════════════════════════════════════
function renderResults(d) {
  document.getElementById('progress-wrap').classList.remove('show');
  document.getElementById('results').classList.add('show');
  document.getElementById('ai-summary').textContent = d.summary || 'No summary generated.';

  const eda = d.eda_report;
  document.getElementById('stat-grid').innerHTML = `
    ${statCard(d.original_shape.rows,    'Original Rows',  '')}
    ${statCard(d.cleaned_shape.rows,     'Cleaned Rows',   'green')}
    ${statCard(eda.total_missing,        'Missing Cells',  eda.total_missing  > 0 ? 'amber' : 'green')}
    ${statCard(eda.duplicate_rows,       'Duplicates',     eda.duplicate_rows > 0 ? 'red'   : 'green')}
    ${statCard(d.original_shape.columns, 'Orig. Columns',  '')}
    ${statCard(d.cleaned_shape.columns,  'Final Columns',  'blue')}
  `;

  const cols = eda.columns || {};
  document.getElementById('col-grid').innerHTML =
    Object.entries(cols).map(([n,i]) => colCard(n, i, d.cleaned_data?.length || 1)).join('');

  document.getElementById('logs-wrap').innerHTML = (d.logs || []).map((l, i) =>
    `<div class="log-item"><span class="log-num">${String(i+1).padStart(2,'0')}</span><span>${escHtml(l)}</span></div>`
  ).join('');

  tableRows   = d.cleaned_data || [];
  currentPage = 1;
  document.getElementById('table-search').value = '';
  renderTable(tableRows, d.cleaned_columns);
  setTimeout(() => document.getElementById('results').scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
}

function statCard(val, label, cls) {
  return `<div class="stat-card ${cls}"><div class="val">${val}</div><div class="lbl">${label}</div></div>`;
}

function colCard(name, info, total) {
  const isNum   = info.dtype.includes('int') || info.dtype.includes('float');
  const nullPct = info.null_count ? (info.null_count / Math.max(total,1) * 100).toFixed(1) : 0;
  let stats = `
    <div class="col-stat-row"><span>Unique values</span><span>${info.unique_count}</span></div>
    <div class="col-stat-row"><span>Missing</span><span>${info.null_count}</span></div>
  `;
  if (isNum) {
    if (info.mean   != null) stats += `<div class="col-stat-row"><span>Mean</span><span>${info.mean}</span></div>`;
    if (info.median != null) stats += `<div class="col-stat-row"><span>Median</span><span>${info.median}</span></div>`;
    if (info.std    != null) stats += `<div class="col-stat-row"><span>Std Dev</span><span>${info.std}</span></div>`;
  } else if (info.top_values) {
    const top = Object.entries(info.top_values).slice(0,2).map(([k,v])=>`${escHtml(k)} (${v})`).join(', ');
    stats += `<div class="col-stat-row"><span>Top values</span><span>${top||'—'}</span></div>`;
  }
  const bar = info.null_count > 0
    ? `<div class="missing-bar-wrap"><div class="missing-bar-label"><span>Missing %</span><span>${nullPct}%</span></div><div class="missing-bar"><div class="missing-bar-fill" style="width:${Math.min(nullPct,100)}%"></div></div></div>`
    : '';
  return `<div class="col-card"><div class="col-card-head"><div class="col-name">${escHtml(name)}</div><span class="dtype-badge ${isNum?'dtype-num':'dtype-cat'}">${isNum?'numeric':'categorical'}</span></div>${stats}${bar}</div>`;
}

// ════════════════════════════════════════════
//  TABLE
// ════════════════════════════════════════════
function renderTable(rows, cols) {
  const q        = document.getElementById('table-search').value.toLowerCase().trim();
  const filtered = q ? rows.filter(r => Object.values(r).some(v => String(v).toLowerCase().includes(q))) : rows;
  const total    = filtered.length;
  const pages    = Math.max(1, Math.ceil(total / PAGE_SIZE));
  currentPage    = Math.min(currentPage, pages);
  const start    = (currentPage - 1) * PAGE_SIZE;
  const slice    = filtered.slice(start, start + PAGE_SIZE);
  const colNames = cols || Object.keys(rows[0] || {});

  document.getElementById('table-head').innerHTML =
    '<tr>' + colNames.map(c => `<th>${escHtml(c)}</th>`).join('') + '</tr>';
  document.getElementById('table-body').innerHTML = slice.map(row =>
    '<tr>' + colNames.map(c => {
      const v = row[c];
      if (v === null || v === undefined || v === '') return `<td class="null-cell">null</td>`;
      const cls = String(c).endsWith('_encoded') ? 'enc-cell' : '';
      return `<td class="${cls}" title="${escHtml(String(v))}">${escHtml(String(v))}</td>`;
    }).join('') + '</tr>'
  ).join('');

  document.getElementById('table-info').innerHTML =
    `Showing <strong>${start+1}–${Math.min(start+PAGE_SIZE,total)}</strong> of <strong>${total}</strong> rows`;

  const pg = document.getElementById('pagination');
  pg.innerHTML = '';
  const prev = document.createElement('button');
  prev.className = 'pg-btn'; prev.textContent = '← Prev'; prev.disabled = currentPage === 1;
  prev.onclick = () => { currentPage--; renderTable(rows, cols); };
  pg.appendChild(prev);
  const span = document.createElement('span');
  span.className = 'pg-info'; span.textContent = `Page ${currentPage} / ${pages}`;
  pg.appendChild(span);
  const next = document.createElement('button');
  next.className = 'pg-btn'; next.textContent = 'Next →'; next.disabled = currentPage === pages;
  next.onclick = () => { currentPage++; renderTable(rows, cols); };
  pg.appendChild(next);
}

document.getElementById('table-search').addEventListener('input', () => {
  currentPage = 1;
  if (currentData) renderTable(currentData.cleaned_data, currentData.cleaned_columns);
});

// ════════════════════════════════════════════
//  DOWNLOADS & ACTIONS
// ════════════════════════════════════════════
document.getElementById('btn-dl-csv').addEventListener('click', async () => {
  if (isViewingHistory) {
    if (!currentData?.cleaned_data || !currentData?.cleaned_columns) return;
    const cols = currentData.cleaned_columns;
    const rows = currentData.cleaned_data;
    const csv  = [cols.join(','), ...rows.map(r => cols.map(c => JSON.stringify(r[c] ?? '')).join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url  = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'cleaned_analysis.csv'; a.click();
    URL.revokeObjectURL(url);
    return;
  }
  if (!selectedFile) return;
  const fd = new FormData(); fd.append('file', selectedFile);
  try {
    const res = await fetch(`${API}/download`, { method: 'POST', body: fd });
    if (!res.ok) throw new Error(`Download failed (${res.status})`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'cleaned_' + selectedFile.name; a.click();
    URL.revokeObjectURL(url);
  } catch (e) { showError('Download failed: ' + e.message); }
});

document.getElementById('btn-dl-json').addEventListener('click', () => {
  if (!currentData) return;
  const blob = new Blob([JSON.stringify(currentData.eda_report, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = 'eda_report.json'; a.click();
  URL.revokeObjectURL(url);
});


document.getElementById('btn-reset').addEventListener('click', () => {
  clearPageContent();
  document.querySelectorAll('.history-item').forEach(e => e.classList.remove('active'));
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

// ════════════════════════════════════════════
//  HELPERS
// ════════════════════════════════════════════
function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ════════════════════════════════════════════
//  INIT
// ════════════════════════════════════════════
renderNav();
if (authToken && authUser) {
  loadHistory();
}