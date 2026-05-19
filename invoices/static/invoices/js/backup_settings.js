(function () {
  function getCsrfToken(form) {
    return form.querySelector('[name="csrfmiddlewaretoken"]')?.value || '';
  }

  function initTabs(container) {
    const tabs = Array.from(container.querySelectorAll('[data-tab-target]'));
    const panels = Array.from(container.querySelectorAll('[data-backup-settings-panel]'));

    const activate = (id) => {
      tabs.forEach((tab) => tab.classList.toggle('is-active', tab.getAttribute('href') === `#${id}`));
      panels.forEach((panel) => panel.classList.toggle('is-active', panel.id === id));
    };

    tabs.forEach((tab) => {
      if (tab.dataset.backupSettingsTabBound === 'true') {
        return;
      }
      tab.dataset.backupSettingsTabBound = 'true';
      tab.addEventListener('click', (event) => {
        event.preventDefault();
        activate(tab.getAttribute('href').substring(1));
      });
    });

    return { activate };
  }

  function bindForm(container, activate) {
    if (container.dataset.backupSettingsFormBound === 'true') {
      return;
    }
    container.dataset.backupSettingsFormBound = 'true';

    let isSubmitting = false;
    let activeSubmitter = null;

    const submitWithAction = async (form, submitter) => {
      const panel = container.querySelector('#backup-settings-panel');
      const badgeContainer = document.querySelector('[data-backup-settings-status-badge-container]');
      if (!form || !panel || !badgeContainer || !submitter || submitter.name !== 'action' || isSubmitting) {
        return;
      }

      isSubmitting = true;
      activate('backup-settings-panel');

      const formData = new FormData(form);
      formData.set(submitter.name, submitter.value);

      const buttons = form.querySelectorAll('button');
      buttons.forEach((button) => {
        button.disabled = true;
      });

      try {
        const response = await fetch(form.getAttribute('action') || window.location.href, {
          method: 'POST',
          body: formData,
          headers: {
            'X-CSRFToken': getCsrfToken(form),
            'X-Requested-With': 'XMLHttpRequest',
          },
        });
        const payload = await response.json();
        if (!payload || !payload.fragments) {
          throw new Error('Invalid backup settings response');
        }

        panel.innerHTML = payload.fragments.settings_panel;
        badgeContainer.innerHTML = payload.fragments.status_badge;
        activate(payload.active_tab || 'backup-settings-panel');
      } catch (error) {
        window.location.reload();
      } finally {
        isSubmitting = false;
        buttons.forEach((button) => {
          button.disabled = false;
        });
      }
    };

    container.addEventListener('click', (event) => {
      const submitter = event.target.closest('[data-backup-settings-form] button[name="action"]');
      if (!submitter) {
        return;
      }

      activeSubmitter = submitter;
      event.preventDefault();
      submitWithAction(submitter.form, submitter);
    });

    container.addEventListener('submit', async (event) => {
      const form = event.target.closest('[data-backup-settings-form]');
      if (!form) {
        return;
      }

      event.preventDefault();
      const submitter = event.submitter || activeSubmitter || document.activeElement;
      activeSubmitter = null;
      await submitWithAction(form, submitter);
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    const container = document.querySelector('[data-backup-settings-tabs]');
    if (!container) {
      return;
    }

    const { activate } = initTabs(container);
    bindForm(container, activate);
  });
})();
