(function () {
  function parseNumber(value) {
    const num = parseFloat(value);
    return Number.isFinite(num) ? num : 0;
  }

  function isDeleted(row) {
    if (row.classList.contains('order-line--deleted')) {
      return true;
    }
    if (row.hidden) {
      return true;
    }
    const deleteInput = row.querySelector('input[name$="-DELETE"]');
    if (!deleteInput) {
      return false;
    }
    if (deleteInput.type === 'checkbox') {
      return deleteInput.checked;
    }
    return (
      deleteInput.value === 'on' ||
      deleteInput.value === 'true' ||
      deleteInput.value === '1'
    );
  }

  function formatCurrency(value, symbol) {
    const amount = Number.isFinite(value) ? value : 0;
    const formatted = amount.toFixed(2);
    return `${formatted} ${symbol}`.trim();
  }

  function collectRows(form) {
    return Array.from(form.querySelectorAll('.formsetDynamic'));
  }

  function getLineType(row) {
    const select = row.querySelector('select[name$="-line_type"]');
    if (!select) {
      return 'quantity';
    }
    return select.value || 'quantity';
  }

  function computeRowTotal(row) {
    const type = getLineType(row);
    const unitPriceInput = row.querySelector('input[name$="-unit_price"]');
    const quantityInput = row.querySelector('input[name$="-quantity"]');
    const descriptionInput = row.querySelector('input[name$="-description"]');

    const description = descriptionInput ? descriptionInput.value.trim() : '';
    const unitPrice = parseNumber(unitPriceInput ? unitPriceInput.value : 0);
    const quantity = parseNumber(quantityInput ? quantityInput.value : 0);

    if (!description && !unitPrice && !quantity) {
      return 0;
    }

    if (type === 'flat') {
      return unitPrice;
    }
    return quantity * unitPrice;
  }

  function updateSummary(form) {
    const summary = form.querySelector('[data-invoice-totals-summary]');
    if (!summary) {
      return;
    }
    const currency = form.dataset.currencySymbol || '€';
    const discountRate = parseNumber(form.dataset.discountRate || '0');
    const taxRate = parseNumber(form.dataset.taxRate || '0');

    let subTotal = 0;
    collectRows(form).forEach((row) => {
      if (isDeleted(row)) {
        return;
      }
      subTotal += computeRowTotal(row);
    });

    const discountAmount = subTotal * (discountRate / 100);
    const taxBase = subTotal - discountAmount;
    const taxAmount = taxBase * (taxRate / 100);
    const total = taxBase + taxAmount;

    const fieldMap = {
      sub: subTotal,
      discount: discountAmount,
      tax: taxAmount,
      total,
    };

    Object.entries(fieldMap).forEach(([key, value]) => {
      const target = summary.querySelector(`[data-total-${key}]`);
      if (target) {
        target.textContent = formatCurrency(value, currency);
      }
    });
  }

  function init(form) {
    if (!form || form.dataset.invoiceTotalsInitialised) {
      return;
    }
    form.dataset.invoiceTotalsInitialised = 'true';

    form.addEventListener('orderline:update', () => updateSummary(form));
    updateSummary(form);
  }

  document.addEventListener('DOMContentLoaded', () => {
    document
      .querySelectorAll('[data-invoice-totals]')
      .forEach((form) => init(form));
  });

  window.invoiceTotals = window.invoiceTotals || {};
  window.invoiceTotals.init = (root) => {
    if (!root) {
      return;
    }
    if (root.matches && root.matches('[data-invoice-totals]')) {
      init(root);
      updateSummary(root);
      return;
    }
    root
      .querySelectorAll('[data-invoice-totals]')
      .forEach((form) => {
        init(form);
        updateSummary(form);
      });
  };
})();
