(function () {
  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  }

  function setToggleState(toggle, isVisible) {
    toggle.setAttribute('aria-pressed', isVisible ? 'true' : 'false');
    toggle.classList.toggle('is-active', isVisible);
  }

  function setToggleInteractivity(toggle, isLocked) {
    toggle.setAttribute('aria-disabled', isLocked ? 'true' : 'false');
    toggle.setAttribute('data-dashboard-chart-toggle-locked', isLocked ? 'true' : 'false');
    toggle.classList.toggle('is-locked', isLocked);
  }

  function setSeriesVisibility(chart, seriesName, isVisible) {
    const series = chart.querySelectorAll(`[data-dashboard-chart-series="${seriesName}"]`);
    series.forEach((item) => {
      item.hidden = !isVisible;
    });
  }

  function setupChart(chart) {
    const toggles = chart.querySelectorAll('[data-dashboard-chart-toggle]');

    if (!toggles.length) {
      return;
    }

    const visibleSeries = new Set(['revenue', 'expense']);

    function syncChartState() {
      toggles.forEach((button) => {
        const buttonSeries = button.getAttribute('data-dashboard-chart-toggle');
        if (!buttonSeries) {
          return;
        }

        const isVisible = visibleSeries.has(buttonSeries);
        const isLocked = visibleSeries.size === 1 && isVisible;

        setToggleState(button, isVisible);
        setToggleInteractivity(button, isLocked);
        setSeriesVisibility(chart, buttonSeries, isVisible);
      });
    }

    toggles.forEach((toggle) => {
      const seriesName = toggle.getAttribute('data-dashboard-chart-toggle');

      if (!seriesName) {
        return;
      }

      toggle.addEventListener('click', () => {
        if (toggle.getAttribute('aria-disabled') === 'true') {
          return;
        }

        if (visibleSeries.has(seriesName)) {
          visibleSeries.delete(seriesName);
        } else {
          visibleSeries.add(seriesName);
        }

        syncChartState();
      });
    });

    syncChartState();
  }

  ready(() => {
    const charts = document.querySelectorAll('[data-dashboard-chart]');
    charts.forEach(setupChart);
  });
})();
