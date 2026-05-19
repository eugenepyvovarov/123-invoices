(function () {
  const SCRIPT_ID = 'customer-payment-config';

  function toMap(list) {
    const map = {};
    if (!Array.isArray(list)) {
      return map;
    }
    list.forEach((item) => {
      if (!item || item.id === undefined || item.id === null) {
        return;
      }
      map[String(item.id)] = item;
    });
    return map;
  }

  function parseScript(id) {
    const el = document.getElementById(id);
    if (!el) {
      return null;
    }
    try {
      return JSON.parse(el.textContent);
    } catch (error) {
      return null;
    } finally {
      el.remove();
    }
  }

  function ensureData() {
    if (!window.__invoicePaymentData) {
      window.__invoicePaymentData = { paymentTerms: {}, projects: {}, customers: {} };
    }
    if (!window.__invoicePaymentData.customers || Object.keys(window.__invoicePaymentData.customers).length === 0) {
      const customers = toMap(parseScript(SCRIPT_ID));
      window.__invoicePaymentData.customers = customers;
    }
    return window.__invoicePaymentData.customers || {};
  }

  function initForm(form) {
    if (!form || form.dataset.projectFormInitialised) {
      return;
    }
    form.dataset.projectFormInitialised = 'true';

    const customerSelect = form.querySelector('[name$="customer"]');
    const paymentSelect = form.querySelector('[name$="payment_term"]');
    if (!customerSelect || !paymentSelect) {
      return;
    }

    const customers = ensureData();

    function applyDefault() {
      const customerId = customerSelect.value;
      if (!customerId) {
        return;
      }
      const info = customers[String(customerId)];
      if (info && info.payment_term) {
        const value = String(info.payment_term);
        if (paymentSelect.value !== value) {
          paymentSelect.value = value;
          paymentSelect.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
    }

    customerSelect.addEventListener('change', applyDefault);

    if (!paymentSelect.value) {
      applyDefault();
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-project-form]').forEach((form) => initForm(form));
  });
})();
