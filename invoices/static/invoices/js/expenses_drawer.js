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

  function parseJsonScript(id) {
    const el = document.getElementById(id);
    if (!el) {
      return null;
    }
    try {
      const data = JSON.parse(el.textContent);
      el.remove();
      return data;
    } catch (error) {
      el.remove();
      return null;
    }
  }

  function buildProjectOptions(select, projects, customerId) {
    if (!select || !projects) {
      return;
    }
    const parsedProjects = Array.isArray(projects) ? projects : [];
    const previous = select.value;
    const targetCustomer = customerId ? parseInt(customerId, 10) : null;
    const allowed = parsedProjects.filter((project) => {
      if (!targetCustomer) {
        return true;
      }
      return project.customer === targetCustomer;
    });
    const placeholder = select.querySelector('option[value=""]');
    select.innerHTML = '';
    if (placeholder) {
      const clone = placeholder.cloneNode(true);
      clone.value = '';
      select.appendChild(clone);
    } else {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = '---------';
      select.appendChild(option);
    }
    allowed.forEach((project) => {
      const option = document.createElement('option');
      option.value = String(project.id);
      option.textContent = project.label || project.id;
      if (project.id === parseInt(previous, 10)) {
        option.selected = true;
      }
      select.appendChild(option);
    });
    if (!select.value && allowed.some((project) => project.id === parseInt(previous, 10))) {
      select.value = String(previous);
    }
  }

  function initDrawerForm(container) {
    const form = container.querySelector('#expense-drawer-form');
    if (!form) {
      return;
    }
    const projectOptions = parseJsonScript('expense-project-options') || [];
    const customerSelect = form.querySelector('[name="customer"]');
    const projectSelect = form.querySelector('[name="project"]');

    if (customerSelect && projectSelect) {
      customerSelect.addEventListener('change', (event) => {
        buildProjectOptions(projectSelect, projectOptions, event.target.value);
      });
      buildProjectOptions(projectSelect, projectOptions, customerSelect.value);
    }

    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const submitButton = form.querySelector('[type="submit"]');
      if (submitButton) {
        submitButton.disabled = true;
      }
      const url = form.getAttribute('action') || window.location.href;
      const formData = new FormData(form);
      formData.set('current_list_url', currentListUrl());
      fetch(url, {
        method: 'POST',
        body: formData,
        headers: {
          'X-CSRFToken': getCsrfToken(),
          'X-Requested-With': 'XMLHttpRequest',
        },
      })
        .then((response) => {
          const contentType = response.headers.get('content-type') || '';
          if (contentType.includes('application/json')) {
            return response.json().then((data) => ({ data, status: response.status, isJson: true }));
          }
          return response
            .text()
            .then((html) => ({ html, status: response.status, isJson: false }));
        })
        .then((payload) => {
          if (payload.isJson) {
            const data = payload.data || {};
            if (data.success) {
              if (data.list_html) {
                replaceExpenseList(data.list_html, data.list_url);
                closeExpenseDrawer();
                showExpenseFeedback(data.message || 'Expense saved successfully.', 'success');
                return;
              }
              if (data.redirect_url) {
                window.location.assign(data.redirect_url);
                return;
              }
              window.location.reload();
              return;
            }
            if (data.html) {
              container.innerHTML = data.html;
              initDrawerForm(container);
            }
            showExpenseFeedback(data.error || 'Unable to save expense. Please review the form.', 'danger');
            return;
          }
          if (payload.html) {
            container.innerHTML = payload.html;
            initDrawerForm(container);
          }
        })
        .catch(() => {
          showExpenseFeedback('Unable to save expense. Please try again.', 'danger');
        })
        .finally(() => {
          if (submitButton) {
            submitButton.disabled = false;
          }
        });
    });
  }

  function loadDrawerContent(contentEl, url) {
    contentEl.innerHTML = '<div class="text-center py-4 text-muted small">Loading…</div>';
    return fetch(url)
      .then((resp) => resp.text())
      .then((html) => {
        contentEl.innerHTML = html;
        initDrawerForm(contentEl);
      });
  }

  function initReportToggles(root) {
    const scope = root || document;
    scope.querySelectorAll('.expense-report-toggle-form').forEach((form) => {
      if (form.dataset.asyncBound === 'true') {
        return;
      }
      form.dataset.asyncBound = 'true';
      const checkbox = form.querySelector('[data-expense-report-toggle]');
      if (!checkbox) {
        return;
      }
      checkbox.addEventListener('change', () => {
        const previousChecked = !checkbox.checked;
        const formData = new FormData(form);
        formData.set('exclude_from_reports', checkbox.checked ? '1' : '0');
        checkbox.disabled = true;
        fetch(form.action, {
          method: 'POST',
          body: formData,
          headers: {
            'X-CSRFToken': getCsrfToken(),
            'X-Requested-With': 'XMLHttpRequest',
          },
        })
          .then((response) => {
            if (!response.ok) {
              throw new Error('Toggle update failed');
            }
            return response.json();
          })
          .then((payload) => {
            if (!payload || payload.success !== true) {
              throw new Error('Toggle update failed');
            }
            checkbox.checked = !!payload.exclude_from_reports;
          })
          .catch(() => {
            checkbox.checked = previousChecked;
          })
          .finally(() => {
            checkbox.disabled = false;
          });
      });
    });
  }

  function currentListUrl() {
    return `${window.location.pathname}${window.location.search}`;
  }

  function showExpenseFeedback(message, level) {
    const feedback = document.querySelector('[data-expense-feedback]');
    if (!feedback || !message) {
      return;
    }
    const alertLevel = level || 'info';
    feedback.innerHTML = `<div class="alert alert-${alertLevel}" role="alert"></div>`;
    const alert = feedback.querySelector('[role="alert"]');
    if (alert) {
      alert.textContent = message;
    }
  }

  function replaceExpenseList(html, listUrl) {
    const results = document.querySelector('[data-expense-list-results]');
    if (!results || !html) {
      return;
    }
    results.innerHTML = html;
    initExpenseListControls(results);
    if (listUrl && listUrl !== currentListUrl()) {
      window.history.replaceState({}, '', listUrl);
    }
  }

  function initBulkSelection(root) {
    const scope = root || document;
    const selectAll = scope.querySelector('#select-all-expenses');
    if (!selectAll || selectAll.dataset.bulkBound === 'true') {
      return;
    }
    selectAll.dataset.bulkBound = 'true';
    selectAll.addEventListener('change', () => {
      document.querySelectorAll('.expense-select').forEach((checkbox) => {
        checkbox.checked = selectAll.checked;
      });
    });
  }

  function initExpenseListControls(root) {
    initBulkSelection(root || document);
    initReportToggles(root || document);
  }

  function closeExpenseDrawer() {
    const drawerEl = document.getElementById('expenseDrawer');
    if (!drawerEl) {
      return;
    }
    drawerEl.classList.remove('is-open');
    drawerEl.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('drawer-open');
  }

  function drawerUrl(expenseId) {
    if (!expenseId || expenseId === 'new') {
      return '/expenses/drawer/';
    }
    return `/expenses/${expenseId}/drawer/`;
  }

  ready(() => {
    const drawerEl = document.getElementById('expenseDrawer');
    const contentEl = document.getElementById('expenseDrawerContent');
    if (!drawerEl || !contentEl) {
      return;
    }

    const bodyClass = 'drawer-open';

    function openDrawer() {
      drawerEl.classList.add('is-open');
      drawerEl.setAttribute('aria-hidden', 'false');
      document.body.classList.add(bodyClass);
      const focusable = drawerEl.querySelector('input, select, textarea, button');
      if (focusable) {
        focusable.focus({ preventScroll: true });
      }
    }

    function closeDrawer() {
      drawerEl.classList.remove('is-open');
      drawerEl.setAttribute('aria-hidden', 'true');
      document.body.classList.remove(bodyClass);
    }

    drawerEl.querySelectorAll('[data-expense-drawer-close]').forEach((btn) => {
      btn.addEventListener('click', (event) => {
        event.preventDefault();
        closeDrawer();
      });
    });

    document.addEventListener('click', (event) => {
      const trigger = event.target.closest('[data-expense-drawer]');
      if (trigger) {
        event.preventDefault();
        const expenseId = trigger.getAttribute('data-expense-id') || trigger.getAttribute('data-expense-drawer');
        loadDrawerContent(contentEl, drawerUrl(expenseId)).then(() => openDrawer());
        return;
      }

      const deleteTrigger = event.target.closest('[data-expense-delete]');
      if (deleteTrigger) {
        event.preventDefault();
        const expenseId = deleteTrigger.getAttribute('data-expense-delete') || deleteTrigger.getAttribute('data-expense-id');
        if (!expenseId) {
          return;
        }
        if (!window.confirm('Delete this expense?')) {
          return;
        }
        const formData = new FormData();
        formData.set('current_list_url', currentListUrl());
        fetch(`/expenses/${expenseId}/delete/`, {
          method: 'POST',
          body: formData,
          headers: {
            'X-CSRFToken': getCsrfToken(),
            'X-Requested-With': 'XMLHttpRequest',
          },
        })
          .then((resp) => resp.json())
          .then((data) => {
            if (data && data.success) {
              if (data.list_html) {
                replaceExpenseList(data.list_html, data.list_url);
                showExpenseFeedback(data.message || 'Expense deleted.', 'success');
                return;
              }
              if (data.redirect_url) {
                window.location.assign(data.redirect_url);
                return;
              }
            }
            showExpenseFeedback((data && data.error) || 'Unable to delete expense. Please try again.', 'danger');
          })
          .catch(() => {
            showExpenseFeedback('Unable to delete expense. Please try again.', 'danger');
          });
      }
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && drawerEl.classList.contains('is-open')) {
        closeDrawer();
      }
    });

    initExpenseListControls(document);
  });
})();
