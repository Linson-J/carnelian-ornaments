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

function initOrderNotifications() {
  const nav = document.getElementById('adminOrderNav');
  const badges = [...document.querySelectorAll('.admin-waiting-order-badge')];
  const countEls = [...document.querySelectorAll('.admin-waiting-order-count')];
  if (!nav || badges.length === 0 || countEls.length === 0 || !window.AdminApi) return;

  const notificationUrl = nav.dataset.notificationUrl;
  if (!notificationUrl) return;

  const storageKey = 'adminLatestSeenOrderId';
  let latestSeen = Number(localStorage.getItem(storageKey) || nav.dataset.latestOrderId || 0);
  const pageLatest = Number(nav.dataset.latestOrderId || 0);
  if (pageLatest > latestSeen) {
    latestSeen = pageLatest;
    localStorage.setItem(storageKey, String(latestSeen));
  }

  function playOrderSound() {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;

    try {
      const ctx = new AudioContext();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, ctx.currentTime);
      osc.frequency.setValueAtTime(660, ctx.currentTime + 0.12);
      gain.gain.setValueAtTime(0.0001, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.08, ctx.currentTime + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.28);

      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.3);
      osc.addEventListener('ended', () => ctx.close());
    } catch (error) {
      console.debug('Order notification sound skipped', error);
    }
  }

  function showOrderPopup(data) {
    const popup = document.getElementById('adminOrderPopup');
    const text = document.getElementById('adminOrderPopupText');
    const action = document.getElementById('adminOrderPopupAction');
    if (!popup || !text || !action) return;

    const label = data.latest_order_label || 'New order';
    const customer = data.latest_order_customer || 'Customer';
    const total = data.latest_order_total ? ` - Rs. ${data.latest_order_total}` : '';

    text.textContent = `${label} from ${customer}${total}`;
    action.href = data.latest_order_url || '/admin-panel/orders/';
    popup.classList.add('show');
    popup.setAttribute('aria-hidden', 'false');

    clearTimeout(showOrderPopup.timer);
    showOrderPopup.timer = setTimeout(() => {
      popup.classList.remove('show');
      popup.setAttribute('aria-hidden', 'true');
    }, 12000);
  }

  document.getElementById('adminOrderPopupClose')?.addEventListener('click', () => {
    const popup = document.getElementById('adminOrderPopup');
    if (popup) {
      popup.classList.remove('show');
      popup.setAttribute('aria-hidden', 'true');
    }
  });

  function updateBadge(waitingCount, isNew) {
    countEls.forEach(countEl => {
      countEl.textContent = waitingCount;
    });
    badges.forEach(badge => {
      badge.classList.toggle('hidden', waitingCount <= 0);
    });
    if (isNew) {
      badges.forEach(badge => {
        badge.classList.remove('has-new');
        void badge.offsetWidth;
        badge.classList.add('has-new');
      });
      showToast(`New order waiting (${waitingCount})`, 'success');
      hideToast(4500);
      playOrderSound();
    }
  }

  async function pollOrderNotifications() {
    try {
      const result = await AdminApi.get(notificationUrl, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      const data = result.data || {};
      const latestOrderId = Number(data.latest_order_id || 0);
      const waitingCount = Number(data.waiting_count || 0);
      const hasNewOrder = latestSeen > 0 && latestOrderId > latestSeen;

      updateBadge(waitingCount, hasNewOrder);
      if (hasNewOrder) {
        showOrderPopup(data);
      }

      if (latestOrderId > latestSeen) {
        latestSeen = latestOrderId;
        localStorage.setItem(storageKey, String(latestSeen));
      }
    } catch (error) {
      if (error.status !== 401) {
        console.debug('Order notification check failed', error);
      }
    }
  }

  updateBadge(Number(countEls[0].textContent || 0), false);
  setInterval(pollOrderNotifications, 20000);
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
  initOrderNotifications();
});
