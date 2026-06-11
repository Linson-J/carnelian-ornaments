/* Centralized admin API service. */
(function (window) {
  const SUCCESS_STATUSES = new Set([200, 201, 202, 204]);

  function getCsrfToken() {
    const input = document.querySelector('[name=csrfmiddlewaretoken]');
    if (input && input.value) return input.value;

    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function isSuccessStatus(status) {
    return SUCCESS_STATUSES.has(status) || (status >= 200 && status < 300);
  }

  async function parseResponse(response) {
    if (response.status === 204) return null;

    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      return response.json();
    }
    return response.text();
  }

  function buildError(response, payload) {
    const message =
      (payload && payload.message) ||
      response.statusText ||
      'Request failed.';
    const error = new Error(message);
    error.status = response.status;
    error.payload = payload;
    error.errors = payload && payload.errors;
    return error;
  }

  async function request(method, url, body, options) {
    const opts = options || {};
    const headers = new Headers(opts.headers || {});
    const isFormData = body instanceof FormData;
    const hasBody = body !== undefined && body !== null;

    if (hasBody && !isFormData && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase())) {
      const csrf = getCsrfToken();
      if (csrf && !headers.has('X-CSRFToken')) {
        headers.set('X-CSRFToken', csrf);
      }
    }

    const response = await fetch(url, {
      method,
      headers,
      credentials: opts.credentials || 'same-origin',
      body: hasBody ? (isFormData ? body : JSON.stringify(body)) : undefined,
    });
    const payload = await parseResponse(response);

    if (!isSuccessStatus(response.status) || (payload && payload.success === false)) {
      throw buildError(response, payload);
    }

    return {
      status: response.status,
      ok: true,
      payload,
      data: payload && Object.prototype.hasOwnProperty.call(payload, 'data')
        ? payload.data
        : payload,
      message: payload && payload.message,
    };
  }

  async function requestText(method, url, body, options) {
    const result = await request(method, url, body, options);
    return typeof result.payload === 'string' ? result.payload : '';
  }

  window.AdminApi = {
    request,
    requestText,
    get: (url, options) => request('GET', url, null, options),
    post: (url, body, options) => request('POST', url, body, options),
    put: (url, body, options) => request('PUT', url, body, options),
    patch: (url, body, options) => request('PATCH', url, body, options),
    delete: (url, options) => request('DELETE', url, null, options),
    getText: (url, options) => requestText('GET', url, null, options),
  };
})(window);
