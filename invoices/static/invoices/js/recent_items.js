(function () {
  if (window.recentItems && window.recentItems.initialized) {
    return;
  }

  const COMPONENT_SELECTOR = '[data-recent-items-component]';
  const initialized = new WeakSet();

  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  }

  function parseInitialItems(component) {
    const scriptId = component.getAttribute('data-recent-items-data-script');
    const script = scriptId ? document.getElementById(scriptId) : null;
    if (!script) {
      return [];
    }
    try {
      return JSON.parse(script.textContent) || [];
    } catch (error) {
      return [];
    }
  }

  function setFieldValue(row, selector, value) {
    const field = row ? row.querySelector(selector) : null;
    if (!field) {
      return;
    }
    field.value = value || '';
    field.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function populateOrderLine(row, item) {
    setFieldValue(row, 'input[name$="-description"]', item.description);
    setFieldValue(row, 'input[name$="-quantity"]', item.quantity);
    setFieldValue(row, 'input[name$="-unit_price"]', item.unit_price);
  }

  function appendCell(row, text, className) {
    const cell = document.createElement('td');
    if (className) {
      cell.className = className;
    }
    cell.textContent = text || '';
    row.appendChild(cell);
    return cell;
  }

  function renderRecentItems(wrapper, items, hasProject, manager) {
    wrapper.innerHTML = '';
    if (!hasProject) {
      wrapper.innerHTML = '<div class="alert alert-info" role="alert">Select a project to see recently used items.</div>';
      return;
    }
    if (!items.length) {
      wrapper.innerHTML = '<div class="alert alert-info" role="alert">No previous items for this project yet.</div>';
      return;
    }

    const card = document.createElement('div');
    card.className = 'card mb-3';
    card.innerHTML = `
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-center mb-2">
          <h5 class="mb-0">Recently used items</h5>
          <small class="text-muted">Click Add to copy details below.</small>
        </div>
        <div class="table-responsive">
          <table class="table table-sm align-middle mb-0">
            <thead>
              <tr>
                <th scope="col">Description</th>
                <th scope="col" class="text-end">Quantity</th>
                <th scope="col" class="text-end">Unit price</th>
                <th scope="col" class="text-end"></th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </div>`;

    const tbody = card.querySelector('tbody');
    items.forEach((item) => {
      const row = document.createElement('tr');
      appendCell(row, item.description || '');
      appendCell(row, item.quantity || '', 'text-end');
      appendCell(row, item.unit_price ? `${item.unit_price} €` : '', 'text-end');
      const actionCell = appendCell(row, '', 'text-end');
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn btn-sm btn-outline-secondary js-add-recent-item';
      button.textContent = 'Add';
      button.addEventListener('click', () => {
        if (!manager) {
          return;
        }
        const targetRow = manager.ensureRow();
        populateOrderLine(targetRow, item);
      });
      actionCell.appendChild(button);
      tbody.appendChild(row);
    });

    wrapper.appendChild(card);
  }

  function setExpanded(component, expanded) {
    const toggle = component.querySelector('[data-recent-items-toggle]');
    const wrapper = component.querySelector('[data-recent-items-wrapper]');
    component.setAttribute('data-recent-items-expanded', expanded ? 'true' : 'false');
    if (toggle) {
      toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
      toggle.textContent = expanded ? 'Hide recent tasks' : 'Show recent tasks';
    }
    if (wrapper) {
      wrapper.hidden = !expanded;
    }
  }

  function init(component) {
    if (!component || initialized.has(component)) {
      return;
    }
    initialized.add(component);

    const wrapper = component.querySelector('[data-recent-items-wrapper]');
    const form = component.closest('form');
    if (!wrapper || !form) {
      return;
    }

    const manager = window.orderLines ? window.orderLines.init(form) : null;
    const template = component.getAttribute('data-recent-items-url-template') || '';
    const projectSelect = form.querySelector('[name="project"]');
    const initialProjectId = component.getAttribute('data-selected-project') || (projectSelect ? projectSelect.value : '');
    const excludeInvoiceId = component.getAttribute('data-exclude-invoice') || '';
    const initialItems = parseInitialItems(component);

    function render(items, hasProject) {
      renderRecentItems(wrapper, items, hasProject, manager);
    }

    function fetchRecentItems(projectId) {
      if (!projectId) {
        render([], false);
        return;
      }
      if (!template) {
        render([], true);
        return;
      }
      const url = new URL(template.replace('/0/', `/${projectId}/`), window.location.href);
      if (excludeInvoiceId) {
        url.searchParams.set('exclude_invoice', excludeInvoiceId);
      }
      fetch(url)
        .then((response) => response.json())
        .then((data) => {
          render(data.items || [], true);
        })
        .catch(() => {
          render([], true);
        });
    }

    render(initialItems, Boolean(initialProjectId));
    setExpanded(component, component.getAttribute('data-recent-items-expanded') !== 'false');

    const toggle = component.querySelector('[data-recent-items-toggle]');
    if (toggle) {
      toggle.addEventListener('click', () => {
        setExpanded(component, toggle.getAttribute('aria-expanded') !== 'true');
      });
    }

    if (projectSelect) {
      projectSelect.addEventListener('change', (event) => {
        fetchRecentItems(event.target.value);
      });

      if (!initialProjectId && projectSelect.value) {
        fetchRecentItems(projectSelect.value);
      }
    }
  }

  function initAll(root) {
    (root || document)
      .querySelectorAll(COMPONENT_SELECTOR)
      .forEach((component) => init(component));
  }

  window.recentItems = {
    init,
    initAll,
    initialized: true,
  };

  ready(() => initAll(document));
})();
