document.addEventListener('DOMContentLoaded', () => {
  const drawer = document.querySelector('[data-payment-drawer]');
  if (!drawer) return;

  const content = drawer.querySelector('[data-payment-drawer-content]');
  const template = drawer.querySelector('#paymentFormTemplate');

  let postUrl = null;
  let editPaymentId = null;
  const open = () => {
    // Inject the form template if it's not already present.
    if (template && content && !content.querySelector('[data-payment-form]')) {
      const clone = document.importNode(template.content, true);
      content.appendChild(clone);
    }
    // Ensure the form has a submit handler (idempotent binding).
    const form = content.querySelector('[data-payment-form]');
    if (form) {
      form.setAttribute('data-submit-state', 'idle');
      form.setAttribute('data-form-mode', editPaymentId ? 'edit' : 'add');
      attachFormHandler(form);
    }
    // Update UI labels based on mode (add vs edit)
    const heading = drawer.querySelector('#paymentDrawerLabel');
    const submitBtn = content.querySelector('button[type="submit"]');
    if (heading && submitBtn) {
      if (editPaymentId) {
        heading.textContent = 'Edit Payment';
        submitBtn.textContent = 'Save changes';
      } else {
        heading.textContent = 'Add Payment';
        submitBtn.textContent = 'Add payment';
      }
    }
    // Bind project change to refresh outstanding invoices list (only if project is enabled)
    const projectSelect = content.querySelector('#payment_project');
    if (projectSelect && !projectSelect.disabled && !projectSelect.dataset.bound) {
      projectSelect.dataset.bound = '1';
      projectSelect.addEventListener('change', () => refreshOutstanding(projectSelect.value, { clearAmount: true }));
    }
    // If amount is empty or zero, default to selected invoice due
    const amt = content.querySelector('#payment_amount');
    if (amt) {
      const raw = String(amt.value || '').trim();
      const normalized = raw.replace(/,/g, '');
      const asNum = parseFloat(normalized);
      if (!asNum || asNum <= 0) {
        const firstChecked = content.querySelector('tbody input[name="apply_to"]:checked');
        const due = firstChecked && firstChecked.getAttribute('data-due');
        if (due) {
          amt.value = due;
        }
      }
    }
    drawer.setAttribute('aria-hidden', 'false');
    drawer.setAttribute('data-drawer-state', 'open');
    drawer.classList.add('is-open');
    document.body.style.overflow = 'hidden';
  };

  async function refreshOutstanding(projectId, opts = {}) {
    const tbody = content.querySelector('table tbody');
    if (!projectId || !tbody) return;
    try {
      const resp = await fetch(`/projects/${projectId}/outstanding-invoices/`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      const data = await resp.json();
      tbody.innerHTML = '';
      if (Array.isArray(data.items)) {
        data.items.forEach((item) => { tbody.appendChild(renderInvoiceRow(item)); });
      }
      if (opts.clearAmount) {
        const amt = content.querySelector('#payment_amount');
        if (amt) amt.value = '';
      }
      if (opts.selectInvoiceIds && opts.selectInvoiceIds.length) {
        opts.selectInvoiceIds.forEach((id) => {
          const box = tbody.querySelector(`input[name="apply_to"][value="${id}"]`);
          if (box) box.checked = true;
        });
      }
    } catch (err) {
      console.error('Failed to load outstanding invoices');
    }
  }

  function renderInvoiceRow(item) {
    const tr = document.createElement('tr');
    tr.setAttribute('data-testid', 'payment-invoice-row');
    tr.innerHTML = `
      <td><input type="checkbox" name="apply_to" value="${item.id}" data-due="${item.amount_due}" data-testid="payment-apply-invoice" /></td>
      <td>#${item.sequence_number || item.id}</td>
      <td>${item.issued_date || ''}</td>
      <td class="text-end">${item.total_due} € <span class="${item.is_overdue ? 'text-danger' : ''}"> (${item.amount_due} €)</span></td>
    `;
    return tr;
  }

  function ensureSelectedInvoices(invoiceDetails) {
    const tbody = content.querySelector('table tbody');
    if (!tbody || !Array.isArray(invoiceDetails)) return;
    invoiceDetails.forEach((it) => {
      let checkbox = tbody.querySelector(`input[name="apply_to"][value="${it.id}"]`);
      if (!checkbox) {
        tbody.appendChild(renderInvoiceRow(it));
        checkbox = tbody.querySelector(`input[name="apply_to"][value="${it.id}"]`);
      }
      if (checkbox) checkbox.checked = true;
    });
  }

  const close = () => {
    drawer.setAttribute('aria-hidden', 'true');
    drawer.setAttribute('data-drawer-state', 'closed');
    drawer.classList.remove('is-open');
    document.body.style.overflow = '';
  };

  function attachFormHandler(form) {
    if (form.dataset.bound === '1') return;
    form.dataset.bound = '1';
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      // Require at least one invoice selected
      const selected = form.querySelectorAll('input[name="apply_to"]:checked');
      if (!selected || selected.length === 0) {
        alert('Select at least one invoice to apply payment.');
        return;
      }
      const url = postUrl || (window.location.pathname.replace(/\/$/, '') + '/payments/add/');
      const formData = new FormData(form);
      // Include payment_id if editing
      const pidField = form.querySelector('[data-payment-id-field]');
      if (pidField && editPaymentId) {
        pidField.value = String(editPaymentId);
        formData.set('payment_id', String(editPaymentId));
      }
      // Normalize amount to dot-decimal before sending (avoid locale commas)
      const amtEl = form.querySelector('#payment_amount');
      if (amtEl) {
        const normalizeDecimal = (raw) => {
          let s = String(raw || '').trim().replace(/[€\s\u00A0]/g, '');
          if (s.includes(',') && !s.includes('.')) {
            s = s.replace(',', '.');
          } else if (s.includes(',') && s.includes('.')) {
            const lastComma = s.lastIndexOf(',');
            const lastDot = s.lastIndexOf('.');
            if (lastComma > lastDot) { // comma as decimal
              s = s.replace(/\./g, '');
              s = s.replace(',', '.');
            } else { // dot as decimal
              s = s.replace(/,/g, '');
            }
          }
          return s;
        };
        formData.set('amount', normalizeDecimal(amtEl.value));
      }
      try {
        form.setAttribute('data-submit-state', 'submitting');
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
          body: formData,
        });
        const result = await response.json();
        if (result && result.ok) {
          form.setAttribute('data-submit-state', 'success');
          close();
          window.location.reload();
        } else {
          form.setAttribute('data-submit-state', 'error');
          alert(result && result.error ? result.error : 'Failed to add payment');
        }
      } catch (err) {
        form.setAttribute('data-submit-state', 'error');
        alert('Failed to add payment');
      }
    });
  }

  // Open via delegated handler so different pages can provide a custom endpoint
  document.addEventListener('click', (e) => {
    const trigger = e.target.closest('[data-payment-drawer-open]');
    if (trigger) {
      e.preventDefault();
      postUrl = trigger.getAttribute('data-payment-post') || null;
      editPaymentId = null;
      open();
      return;
    }
    const editBtn = e.target.closest('[data-payment-edit]');
    if (editBtn) {
      e.preventDefault();
      postUrl = editBtn.getAttribute('data-payment-post') || null;
      editPaymentId = (editBtn.getAttribute('data-payment-id') || '').replace(/[^0-9]/g, '');
      open();
      // Prefill
      (async () => {
        try {
          const resp = await fetch(`/invoices/payments/${editPaymentId}/prefill/`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
          const json = await resp.json();
          if (!json || !json.ok) return;
          const p = json.payment;
          const form = content.querySelector('[data-payment-form]');
          if (!form) return;
          const amt = form.querySelector('#payment_amount');
          const date = form.querySelector('#payment_date');
          const memo = form.querySelector('#payment_memo');
          const projectSelect = form.querySelector('#payment_project');
          const idField = form.querySelector('[data-payment-id-field]');
          if (idField) idField.value = String(p.id);
          if (amt) amt.value = p.amount;
          if (date) date.value = p.received_at;
          if (memo) memo.value = p.memo || '';
          if (projectSelect && p.project_id) {
            projectSelect.value = String(p.project_id);
            await refreshOutstanding(p.project_id, { selectInvoiceIds: p.invoice_ids });
            ensureSelectedInvoices(p.invoices);
          } else if (Array.isArray(p.invoices) && p.invoices.length) {
            const tbody = content.querySelector('table tbody');
            if (tbody) {
              tbody.innerHTML = '';
              p.invoices.forEach((it) => tbody.appendChild(renderInvoiceRow(it)));
              ensureSelectedInvoices(p.invoices);
            }
          }
        } catch (err) {
          console.error('Failed to prefill payment');
        }
      })();
    }
    const delBtn = e.target.closest('[data-payment-delete]');
    if (delBtn) {
      e.preventDefault();
      const url = delBtn.getAttribute('data-delete-url');
      if (!url) return;
      if (!confirm('Delete this payment?')) return;
      // CSRF from cookie
      const csrf = (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [])[1];
      fetch(url, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrf || '' } })
        .then((r) => r.json())
        .then((res) => { if (res && res.ok) window.location.reload(); else alert('Failed to delete payment'); })
        .catch(() => alert('Failed to delete payment'));
    }
  });
  // Use event delegation so buttons added later (e.g., Cancel in template)
  // can close the drawer without needing re-binding.
  drawer.addEventListener('click', (e) => {
    const trigger = e.target.closest('[data-payment-drawer-close]');
    if (trigger) {
      e.preventDefault();
      close();
    }
  });
});
