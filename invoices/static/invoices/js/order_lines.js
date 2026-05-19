(function () {
  const FORMSET_ATTR = 'data-order-lines-formset';
  const managers = new WeakMap();
  const LINE_TYPE_FLAT = 'flat';
  const LINE_TYPE_QUANTITY = 'quantity';

  function getIndexFromString(value, formsetName) {
    if (!value) {
      return null;
    }
    const regex = new RegExp(`${formsetName}_set-(\\d+)-`);
    const match = value.match(regex);
    return match ? parseInt(match[1], 10) : null;
  }

  function parseNumber(value) {
    const num = parseFloat(value);
    return Number.isFinite(num) ? num : 0;
  }

  function getDeleteInput(formsetName, row) {
    return row.querySelector(
      `input[name^="${formsetName}_set"][name$="-DELETE"]`
    );
  }

  function isRowDeleted(formsetName, row) {
    const deleteInput = getDeleteInput(formsetName, row);
    if (!deleteInput) {
      return row.classList.contains('order-line--deleted');
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

  function setWarning(row, message) {
    const warningEl = row.querySelector('[data-order-line-warning]');
    if (!warningEl) {
      return;
    }
    warningEl.textContent = message || '';
  }

  class OrderLineManager {
    constructor(form) {
      this.form = form;
      this.formsetName = form.getAttribute(FORMSET_ATTR) || 'orderline';
      this.totalInput = form.querySelector(
        `input[name="${this.formsetName}_set-TOTAL_FORMS"]`
      );
    }

    init() {
      if (managers.get(this.form)) {
        return managers.get(this.form);
      }

      this.form.addEventListener('click', (event) => this.handleClick(event));
      this.form.addEventListener('change', (event) => this.handleChange(event));
      this.form.addEventListener('input', (event) => this.handleInput(event));

      managers.set(this.form, this);
      this.refreshRowStates();
      this.updateRemoveButtons();
      this.triggerUpdate();
      return this;
    }

    rows() {
      return Array.from(this.form.querySelectorAll('.formsetDynamic'));
    }

    activeRows() {
      return this.rows().filter((row) => !isRowDeleted(this.formsetName, row));
    }

    totalCount() {
      return parseInt(this.totalInput?.value || '0', 10);
    }

    getRowIndex(row) {
      const idInput = row.querySelector(
        `input[id^="id_${this.formsetName}_set"]`
      );
      if (!idInput) {
        return null;
      }
      return getIndexFromString(idInput.id, this.formsetName);
    }

    handleClick(event) {
      const addButton = event.target.closest('.js-orderline-add');
      if (addButton) {
        event.preventDefault();
        const reference = addButton.closest('.formsetDynamic');
        this.addRow(reference);
        return;
      }

      const removeButton = event.target.closest('.js-orderline-remove');
      if (removeButton) {
        event.preventDefault();
        const row = removeButton.closest('.formsetDynamic');
        if (row) {
          this.removeRow(row);
        }
      }
    }

    handleChange(event) {
      const row = event.target.closest('.formsetDynamic');
      if (!row) {
        return;
      }
      if (event.target.matches(`select[name^="${this.formsetName}_set"][name$="-line_type"]`)) {
        this.applyRowState(row);
        this.triggerUpdate();
      }
    }

    handleInput(event) {
      const row = event.target.closest('.formsetDynamic');
      if (!row) {
        return;
      }
      if (
        event.target.matches(`input[name^="${this.formsetName}_set"][name$="-quantity"]`) ||
        event.target.matches(`input[name^="${this.formsetName}_set"][name$="-unit_price"]`) ||
        event.target.matches(`input[name^="${this.formsetName}_set"][name$="-description"]`)
      ) {
        this.updateRowWarning(row);
        this.triggerUpdate();
      }
    }

    addRow(referenceRow) {
      const activeRows = this.activeRows();
      const baseRow =
        referenceRow ||
        activeRows[activeRows.length - 1] ||
        this.rows()[this.rows().length - 1];
      if (!baseRow) {
        return null;
      }

      const clone = baseRow.cloneNode(true);
      const oldIndex = this.getRowIndex(baseRow);
      const newIndex = this.totalCount();

      this.updateRowAttributes(clone, oldIndex, newIndex);
      this.clearRow(clone);
      baseRow.after(clone);

      if (this.totalInput) {
        this.totalInput.value = newIndex + 1;
      }

      this.updateRemoveButtons();
      this.applyRowState(clone);
      this.triggerUpdate();
      return clone;
    }

    removeRow(row) {
      const deleteInput = getDeleteInput(this.formsetName, row);
      const singleActive = this.activeRows().length <= 1;

      if (deleteInput) {
        if (deleteInput.type === 'checkbox') {
          deleteInput.checked = true;
        } else {
          deleteInput.value = 'on';
        }
      }

      row.classList.add('order-line--deleted');
      row.hidden = true;

      if (singleActive) {
        const replacement = this.addRow(row);
        if (replacement) {
          this.clearRow(replacement);
          this.applyRowState(replacement);
        }
      }

      this.updateRemoveButtons();
      this.triggerUpdate();
    }

    ensureRow() {
      const deletedRow = this.rows().find((row) => isRowDeleted(this.formsetName, row));
      if (deletedRow) {
        this.reviveRow(deletedRow);
        this.clearRow(deletedRow);
        this.applyRowState(deletedRow);
        this.triggerUpdate();
        return deletedRow;
      }

      const emptyRow = this.activeRows().find((row) => this.isRowEmpty(row));
      if (emptyRow) {
        return emptyRow;
      }

      return this.addRow(this.rows()[this.rows().length - 1]);
    }

    reviveRow(row) {
      const deleteInput = getDeleteInput(this.formsetName, row);
      if (deleteInput) {
        if (deleteInput.type === 'checkbox') {
          deleteInput.checked = false;
        } else {
          deleteInput.value = '';
        }
      }
      row.classList.remove('order-line--deleted');
      row.hidden = false;
      this.updateRemoveButtons();
    }

    clearRow(row) {
      row
        .querySelectorAll('input, textarea, select')
        .forEach((input) => this.resetInput(input));
      row
        .querySelectorAll('.is-invalid')
        .forEach((el) => el.classList.remove('is-invalid'));
      row
        .querySelectorAll('.invalid-feedback, .form-field__error')
        .forEach((el) => el.remove());
      setWarning(row, '');

      const typeSelect = row.querySelector(
        `select[name^="${this.formsetName}_set"][name$="-line_type"]`
      );
      if (typeSelect) {
        typeSelect.value = LINE_TYPE_QUANTITY;
      }
      const quantityInput = row.querySelector(
        `input[name^="${this.formsetName}_set"][name$="-quantity"]`
      );
      if (quantityInput) {
        quantityInput.value = '0.00';
        quantityInput.readOnly = false;
        quantityInput.classList.remove('order-line-quantity--readonly', 'order-line-input--invalid');
      }
      const unitPriceInput = row.querySelector(
        `input[name^="${this.formsetName}_set"][name$="-unit_price"]`
      );
      if (unitPriceInput) {
        unitPriceInput.value = '0.00';
      }
      this.applyRowState(row);
    }

    resetInput(input) {
      if (input.name && input.name.endsWith('-DELETE')) {
        if (input.type === 'checkbox') {
          input.checked = false;
        } else {
          input.value = '';
        }
        return;
      }

      if (input.name && input.name.endsWith('-id')) {
        input.value = '';
        return;
      }

      if (input.type === 'checkbox' || input.type === 'radio') {
        input.checked = false;
        return;
      }

      if (input.tagName === 'SELECT') {
        input.selectedIndex = 0;
        return;
      }

      if (
        input.type === 'text' ||
        input.type === 'number' ||
        input.tagName === 'TEXTAREA' ||
        input.type === 'hidden'
      ) {
        input.value = '';
      }
    }

    isRowEmpty(row) {
      const description = row.querySelector(`input[name^="${this.formsetName}_set"][name$="-description"]`);
      const quantity = row.querySelector(`input[name^="${this.formsetName}_set"][name$="-quantity"]`);
      const unitPrice = row.querySelector(`input[name^="${this.formsetName}_set"][name$="-unit_price"]`);

      return (
        (!description || description.value.trim() === '') &&
        (!quantity || quantity.value === '' || Number(quantity.value) === 0) &&
        (!unitPrice || unitPrice.value === '' || Number(unitPrice.value) === 0)
      );
    }

    updateRowAttributes(row, oldIndex, newIndex) {
      const pattern =
        oldIndex === null
          ? new RegExp(`${this.formsetName}_set-\\d+-`, 'g')
          : new RegExp(`${this.formsetName}_set-${oldIndex}-`, 'g');
      const replacement = `${this.formsetName}_set-${newIndex}-`;

      row.querySelectorAll('[name]').forEach((el) => {
        el.name = el.name.replace(pattern, replacement);
      });
      row.querySelectorAll('[id]').forEach((el) => {
        el.id = el.id.replace(pattern, replacement);
      });
      row.querySelectorAll('label[for]').forEach((label) => {
        label.htmlFor = label.htmlFor.replace(pattern, replacement);
      });
      row.classList.remove('order-line--deleted');
      row.hidden = false;
    }

    updateRemoveButtons() {
      const activeCount = this.activeRows().length;
      const disable = activeCount <= 1;
      this.rows().forEach((row) => {
        const removeBtn = row.querySelector('.js-orderline-remove');
        if (removeBtn) {
          removeBtn.disabled = disable;
        }
      });
    }

    refreshRowStates() {
      this.rows().forEach((row) => this.applyRowState(row));
    }

    applyRowState(row) {
      const typeSelect = row.querySelector(
        `select[name^="${this.formsetName}_set"][name$="-line_type"]`
      );
      const quantityInput = row.querySelector(
        `input[name^="${this.formsetName}_set"][name$="-quantity"]`
      );
      const typeValue = typeSelect ? typeSelect.value : LINE_TYPE_QUANTITY;
      row.dataset.lineType = typeValue;

      if (typeValue === LINE_TYPE_FLAT) {
        row.classList.add('order-line--flat');
        if (quantityInput) {
          quantityInput.value = '1.00';
          quantityInput.readOnly = true;
          quantityInput.classList.add('order-line-quantity--readonly');
          quantityInput.classList.remove('order-line-input--invalid');
        }
      } else {
        row.classList.remove('order-line--flat');
        if (quantityInput) {
          quantityInput.readOnly = false;
          quantityInput.classList.remove('order-line-quantity--readonly');
        }
      }

      this.updateRowWarning(row);
    }

    updateRowWarning(row) {
      const typeValue = row.dataset.lineType || LINE_TYPE_QUANTITY;
      const quantityInput = row.querySelector(
        `input[name^="${this.formsetName}_set"][name$="-quantity"]`
      );
      const priceInput = row.querySelector(
        `input[name^="${this.formsetName}_set"][name$="-unit_price"]`
      );
      const quantity = parseNumber(quantityInput ? quantityInput.value : 0);
      const price = parseNumber(priceInput ? priceInput.value : 0);

      if (quantityInput) {
        quantityInput.classList.remove('order-line-input--invalid');
      }

      if (typeValue !== LINE_TYPE_FLAT && price > 0 && quantity <= 0) {
        setWarning(row, '');
        if (quantityInput) {
          quantityInput.classList.add('order-line-input--invalid');
        }
      } else {
        setWarning(row, '');
      }
    }

    triggerUpdate() {
      const event = new CustomEvent('orderline:update', {
        bubbles: true,
        detail: { form: this.form },
      });
      this.form.dispatchEvent(event);
    }
  }

  function initManager(form) {
    if (!form) {
      return null;
    }
    const existing = managers.get(form);
    if (existing) {
      return existing;
    }
    const manager = new OrderLineManager(form).init();
    return manager;
  }

  window.orderLines = {
    init(form) {
      return initManager(form);
    },
    get(form) {
      return managers.get(form);
    },
  };

  document.addEventListener('DOMContentLoaded', () => {
    document
      .querySelectorAll(`[${FORMSET_ATTR}]`)
      .forEach((form) => initManager(form));
  });
})();
