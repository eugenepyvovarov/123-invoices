document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-expense-import-selection]').forEach((form) => {
    const selectAll = form.querySelector('[data-expense-import-select-all]');
    const rows = Array.from(form.querySelectorAll('[data-expense-import-row]'));
    if (!selectAll || rows.length === 0) return;

    const refreshSelectAll = () => {
      const checked = rows.filter((row) => row.checked).length;
      selectAll.checked = checked === rows.length;
      selectAll.indeterminate = checked > 0 && checked < rows.length;
    };

    selectAll.addEventListener('change', () => {
      rows.forEach((row) => {
        row.checked = selectAll.checked;
      });
      refreshSelectAll();
    });
    rows.forEach((row) => row.addEventListener('change', refreshSelectAll));
    refreshSelectAll();
  });
});
