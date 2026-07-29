(function () {
  function getMessage(form) {
    return form.querySelector('[data-newsletter-message]');
  }

  function setMessage(form, text, type) {
    const message = getMessage(form);
    if (!message) return;
    message.textContent = text;
    message.dataset.state = type || '';
  }

  function isValidEmail(value) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  }

  async function submitNewsletter(form) {
    const input = form.querySelector('input[name="email"]');
    const button = form.querySelector('[data-newsletter-submit]');
    const email = input ? input.value.trim() : '';

    if (!isValidEmail(email)) {
      setMessage(form, 'Enter a valid email address.', 'error');
      if (input) input.focus();
      return;
    }

    const originalText = button ? button.textContent : '';
    if (button) {
      button.disabled = true;
      button.textContent = 'Subscribing...';
    }
    setMessage(form, '', '');

    try {
      const response = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: {
          Accept: 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'same-origin',
      });
      const payload = await response.json();
      if (!response.ok || payload.success === false) {
        throw new Error(payload.message || 'Could not subscribe right now.');
      }
      form.reset();
      setMessage(form, payload.message || 'Thanks for subscribing.', 'success');
    } catch (error) {
      setMessage(form, error.message || 'Could not subscribe right now.', 'error');
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = originalText;
      }
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-newsletter-form]').forEach(function (form) {
      form.addEventListener('submit', function (event) {
        event.preventDefault();
        submitNewsletter(form);
      });
    });
  });
}());
