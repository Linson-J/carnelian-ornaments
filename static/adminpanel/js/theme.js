function showToast(message, type) {
  const toast = document.getElementById('toast');
  if (!toast) return null;

  const normalizedType = type === 'error' ? 'danger' : (type || 'success');
  toast.textContent = message;
  toast.className = `toast show ${normalizedType}`;
  return toast;
}

function hideToast(delay) {
  const toast = document.getElementById('toast');
  if (!toast) return;
  setTimeout(() => { toast.className = 'toast'; }, delay || 3500);
}

function confirmDelete(id, name) {
  const message = document.getElementById('deleteMsg');
  const form = document.getElementById('deleteForm');
  const overlay = document.getElementById('deleteOverlay');
  if (!message || !form || !overlay) return;

  message.textContent = `Are you sure you want to delete "${name}"? This will also delete all its images permanently.`;
  form.action = `/admin-panel/products/${id}/delete/`;
  overlay.classList.add('open');
}

function closeModal() {
  const overlay = document.getElementById('deleteOverlay');
  if (overlay) overlay.classList.remove('open');
}

function initUrlToast() {
  const params = new URLSearchParams(location.search);
  const message = params.get('msg');
  if (!message) return;

  showToast(decodeURIComponent(message.replace(/\+/g, ' ')), params.get('type') || 'success');
  hideToast(3500);
  history.replaceState(null, '', location.pathname);
}

function initClock() {
  const element = document.getElementById('clock');
  if (!element) return;

  function tick() {
    element.textContent = new Date().toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  }

  tick();
  setInterval(tick, 1000);
}

function debounce(fn, delay) {
  let timer;
  return function debounced() {
    const args = arguments;
    const context = this;
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(context, args), delay);
  };
}

function initProductLiveSearch() {
  const searchInput = document.querySelector('form.filters input[name="search"]');
  if (!searchInput || !window.AdminApi) return;

  const form = searchInput.closest('form');
  const tbody = document.querySelector('table tbody');
  const updateResults = debounce(async () => {
    const params = new URLSearchParams(new FormData(form));
    const url = `${location.pathname}?${params.toString()}`;

    try {
      const text = await AdminApi.getText(url, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      const parser = new DOMParser();
      const doc = parser.parseFromString(text, 'text/html');
      const newTbody = doc.querySelector('table tbody');
      if (newTbody && tbody) {
        tbody.innerHTML = newTbody.innerHTML;
      }
      history.replaceState(null, '', url);
    } catch (error) {
      console.error('Live search error', error);
    }
  }, 300);

  searchInput.addEventListener('input', updateResults);
}

function toggleDropdown(event, id) {
  if (event) event.stopPropagation();

  document.querySelectorAll('.actions-dropdown-menu').forEach(menu => {
    if (menu.id !== `dropdown-${id}`) {
      menu.classList.remove('show');
    }
  });

  const menu = document.getElementById(`dropdown-${id}`);
  if (menu) {
    const isShowing = menu.classList.contains('show');
    if (!isShowing) {
      const trigger = event && event.currentTarget ? event.currentTarget : null;
      if (trigger) {
        const rect = trigger.getBoundingClientRect();
        const spaceBelow = window.innerHeight - rect.bottom;
        if (spaceBelow < 180 && rect.top > 180) {
          menu.classList.add('dropup');
        } else {
          menu.classList.remove('dropup');
        }
      }
      menu.classList.add('show');
    } else {
      menu.classList.remove('show');
    }
  }
}

function closeAllDropdowns() {
  document.querySelectorAll('.actions-dropdown-menu.show').forEach(menu => {
    menu.classList.remove('show');
  });
}

window.addEventListener('click', closeAllDropdowns);
window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeAllDropdowns();
});

document.addEventListener('DOMContentLoaded', () => {
  initUrlToast();
  initClock();
  initProductLiveSearch();
});
