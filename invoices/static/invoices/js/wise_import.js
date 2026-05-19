document.addEventListener('DOMContentLoaded', () => {
  const modal = document.querySelector('[data-wise-import-modal]');
  if (!modal) return;

  const body = document.body;
  const form = modal.querySelector('[data-wise-import-form]');
  const statusEl = modal.querySelector('[data-wise-import-status]');
  const submitBtn = modal.querySelector('[data-wise-import-submit]');
  const fileInput = form ? form.querySelector('input[name="statements"]') : null;

  const openModal = () => {
    if (statusEl) {
      statusEl.textContent = '';
      statusEl.classList.remove('text-danger');
      statusEl.setAttribute('data-status-kind', 'idle');
    }
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    modal.setAttribute('data-modal-state', 'open');
    body.style.overflow = 'hidden';
  };

  const closeModal = () => {
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    modal.setAttribute('data-modal-state', 'closed');
    body.style.overflow = '';
    if (form) {
      form.reset();
    }
  };

  document.addEventListener('click', (event) => {
    const openTrigger = event.target.closest('[data-wise-import-open]');
    if (openTrigger) {
      event.preventDefault();
      openModal();
      return;
    }
    const closeTrigger = event.target.closest('[data-wise-import-close]');
    if (closeTrigger) {
      event.preventDefault();
      closeModal();
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && modal.classList.contains('is-open')) {
      closeModal();
    }
  });

  const setStatus = (message, isError = false) => {
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.classList.toggle('text-danger', Boolean(isError));
    statusEl.setAttribute('data-status-kind', isError ? 'error' : (message ? 'success' : 'idle'));
  };

  if (form) {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
        setStatus('Select at least one CSV or ZIP statement.', true);
        return;
      }
      const formData = new FormData(form);
      setStatus('Uploading statements…');
      if (statusEl) {
        statusEl.setAttribute('data-status-kind', 'loading');
      }
      if (submitBtn) {
        submitBtn.disabled = true;
      }
      try {
        const response = await fetch('/invoices/payments/import-wise/', {
          method: 'POST',
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
          body: formData,
        });
        const payload = await response.json();
        if (!payload || !payload.ok) {
          const message = payload && payload.error ? payload.error : 'Import failed.';
          throw new Error(message);
        }
        const summary = [
          `Files: ${payload.files_processed || 0}`,
          `Rows: ${payload.rows_processed || 0}`,
          `Created: ${payload.created || 0}`,
          `Skipped existing: ${payload.skipped_existing || 0}`,
          `Missing ref: ${payload.skipped_missing_reference || 0}`,
          `Other types: ${payload.skipped_not_debit || 0}`,
          `Conversions ignored: ${payload.skipped_conversions || 0}`,
        ].join(' • ');
        setStatus(summary, false);
        form.reset();
        if (payload.errors && payload.errors.length) {
          console.warn('Wise import warnings:', payload.errors);
        }
      } catch (error) {
        setStatus(error.message || 'Import failed.', true);
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
        }
      }
    });
  }
});
