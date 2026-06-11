/* ── Admin Panel — Common JS ──────────────────────────────── */

function showToast(message, type) {
  const t = document.getElementById('toast');
  if (!t) return null;
  t.textContent = message;
  t.className = 'toast show ' + (type || 'success');
  return t;
}

function hideToast(delay) {
  const t = document.getElementById('toast');
  if (!t) return;
  setTimeout(function () { t.className = 'toast'; }, delay || 3500);
}

function confirmDelete(id, name) {
  const msg = document.getElementById('deleteMsg');
  const form = document.getElementById('deleteForm');
  const overlay = document.getElementById('deleteOverlay');
  if (!msg || !form || !overlay) return;
  msg.textContent = 'Are you sure you want to delete "' + name + '"? This will also delete all its images permanently.';
  form.action = '/admin-panel/products/' + id + '/delete/';
  overlay.classList.add('open');
}

function closeModal() {
  const overlay = document.getElementById('deleteOverlay');
  if (overlay) overlay.classList.remove('open');
}

function initUrlToast() {
  const params = new URLSearchParams(location.search);
  if (!params.get('msg')) return;
  showToast('✅ ' + decodeURIComponent(params.get('msg').replace(/\+/g, ' ')), params.get('type') || 'success');
  hideToast(3500);
  history.replaceState(null, '', location.pathname);
}

function initClock() {
  const el = document.getElementById('clock');
  if (!el) return;
  function tick() {
    el.textContent = new Date().toLocaleTimeString('en-IN', {
      hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
  }
  tick();
  setInterval(tick, 1000);
}

document.addEventListener('DOMContentLoaded', function () {
  initUrlToast();
  initClock();
  initProductLiveSearch();
});

function debounce(fn, delay) {
  let t;
  return function() {
    const args = arguments;
    const ctx = this;
    clearTimeout(t);
    t = setTimeout(function(){ fn.apply(ctx, args); }, delay);
  };
}

function initProductLiveSearch() {
  const searchInput = document.querySelector('form.filters input[name="search"]');
  if (!searchInput) return;
  const form = searchInput.closest('form');
  const tbody = document.querySelector('table tbody');
  const updateResults = debounce(async function() {
    const params = new URLSearchParams(new FormData(form));
    try {
      const text = await AdminApi.getText(location.pathname + '?' + params.toString(), {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      });
      const parser = new DOMParser();
      const doc = parser.parseFromString(text, 'text/html');
      const newTbody = doc.querySelector('table tbody');
      if (newTbody && tbody) {
        tbody.innerHTML = newTbody.innerHTML;
      }
      history.replaceState(null, '', location.pathname + '?' + params.toString());
    } catch (e) {
      console.error('Live search error', e);
    }
  }, 300);
  searchInput.addEventListener('input', updateResults);
}
