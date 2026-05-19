(function () {
  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  }

  function getCsrfToken() {
    const cookie = document.cookie
      .split('; ')
      .find((row) => row.startsWith('csrftoken='));
    return cookie ? cookie.split('=')[1] : '';
  }

  function setupRecentItems(container) {
    if (window.recentItems && typeof window.recentItems.initAll === 'function') {
      window.recentItems.initAll(container);
    }
  }

  function setupAutosave(form, invoiceId, container) {
    if (!form) {
      return;
    }
    const headerFields = ['reference_number', 'issued_date', 'due_date', 'payment_term', 'status', 'project'];
    headerFields.forEach((name) => {
      const field = form.querySelector(`[name="${name}"]`);
      if (!field) {
        return;
      }
      field.addEventListener('change', () => {
        const fd = new FormData();
        fd.append(name, field.value);
        fetch(`/invoices/${invoiceId}/autosave/`, {
          method: 'POST',
          body: fd,
          headers: { 'X-CSRFToken': getCsrfToken() },
        }).catch(() => {});
      });
    });

    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const fd = new FormData(form);
      fetch(`/invoices/${invoiceId}/drawer/`, {
        method: 'POST',
        body: fd,
        headers: { 'X-CSRFToken': getCsrfToken() },
      })
        .then((resp) => resp.text())
        .then((html) => {
          container.innerHTML = html;
          initDrawerForm(container, invoiceId);
        })
        .catch(() => {});
    });
  }

  function initDrawerForm(container, invoiceId) {
    const form = container.querySelector('#invoice-drawer-form');
    if (!form) {
      return;
    }
    if (window.orderLines) {
      window.orderLines.init(form);
    }
    setupAutosave(form, invoiceId, container);
    setupRecentItems(container);
    if (window.invoiceDates && typeof window.invoiceDates.init === 'function') {
      window.invoiceDates.init(form);
    }
    if (window.invoiceTotals && typeof window.invoiceTotals.init === 'function') {
      window.invoiceTotals.init(form);
    }
  }

  function loadDrawerContent(contentEl, invoiceId) {
    contentEl.setAttribute('data-drawer-content-state', 'loading');
    contentEl.innerHTML =
      '<div class="text-center py-4 text-muted small">Loading…</div>';
    return fetch(`/invoices/${invoiceId}/drawer/`)
      .then((resp) => resp.text())
      .then((html) => {
        contentEl.innerHTML = html;
        contentEl.setAttribute('data-drawer-content-state', 'ready');
        initDrawerForm(contentEl, invoiceId);
      })
      .catch((error) => {
        contentEl.setAttribute('data-drawer-content-state', 'error');
        throw error;
      });
  }

  ready(() => {
    const drawerEl = document.getElementById('invoiceDrawer');
    if (!drawerEl) {
      return;
    }
    const bodyClass = 'drawer-open';
    const contentEl = drawerEl.querySelector('#invoiceDrawerContent');

    function openDrawer() {
      drawerEl.classList.add('is-open');
      drawerEl.setAttribute('aria-hidden', 'false');
      drawerEl.setAttribute('data-drawer-state', 'open');
      document.body.classList.add(bodyClass);
      const focusable = drawerEl.querySelector('input, select, textarea, button');
      if (focusable) {
        focusable.focus({ preventScroll: true });
      }
    }

    function closeDrawer() {
      drawerEl.classList.remove('is-open');
      drawerEl.setAttribute('aria-hidden', 'true');
      drawerEl.setAttribute('data-drawer-state', 'closed');
      document.body.classList.remove(bodyClass);
    }

    document.addEventListener('click', (event) => {
      const closeTrigger = event.target.closest('[data-invoice-drawer-close]');
      if (closeTrigger) {
        event.preventDefault();
        closeDrawer();
        return;
      }

      const trigger = event.target.closest('[data-invoice-drawer]');
      if (!trigger) {
        return;
      }
      event.preventDefault();
      const invoiceId = trigger.getAttribute('data-invoice-drawer');
      if (!invoiceId) {
        return;
      }
      loadDrawerContent(contentEl, invoiceId).then(() => openDrawer());
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && drawerEl.classList.contains('is-open')) {
        closeDrawer();
      }
    });
  });
})();
