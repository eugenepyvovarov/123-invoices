(function () {
  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  }

  ready(() => {
    document.documentElement.classList.add('js');

    const openButton = document.querySelector('[data-nav-open]');
    const drawer = document.querySelector('[data-nav-drawer]');
    const backdrop = document.querySelector('[data-nav-backdrop]');

    if (!openButton || !drawer || !backdrop) {
      return;
    }

    const bodyClass = 'nav-open';
    const mq = window.matchMedia('(max-width: 1100px)');

    function isDrawerMode() {
      return mq.matches;
    }

    function focusFirstInDrawer() {
      const target = drawer.querySelector(
        '[data-nav-close], a, button, input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (!target) {
        return;
      }
      try {
        target.focus({ preventScroll: true });
      } catch {
        target.focus();
      }
    }

    function openDrawer() {
      if (!isDrawerMode()) {
        return;
      }
      document.body.classList.add(bodyClass);
      drawer.setAttribute('aria-hidden', 'false');
      openButton.setAttribute('aria-expanded', 'true');
      focusFirstInDrawer();
    }

    function closeDrawer({ returnFocus = true } = {}) {
      document.body.classList.remove(bodyClass);
      drawer.setAttribute('aria-hidden', isDrawerMode() ? 'true' : 'false');
      openButton.setAttribute('aria-expanded', 'false');
      if (returnFocus) {
        try {
          openButton.focus({ preventScroll: true });
        } catch {
          openButton.focus();
        }
      }
    }

    function syncMode() {
      if (isDrawerMode()) {
        drawer.setAttribute('aria-hidden', document.body.classList.contains(bodyClass) ? 'false' : 'true');
      } else {
        closeDrawer({ returnFocus: false });
      }
    }

    openButton.addEventListener('click', (event) => {
      event.preventDefault();
      if (document.body.classList.contains(bodyClass)) {
        closeDrawer();
        return;
      }
      openDrawer();
    });

    backdrop.addEventListener('click', (event) => {
      event.preventDefault();
      if (document.body.classList.contains(bodyClass)) {
        closeDrawer();
      }
    });

    drawer.addEventListener('click', (event) => {
      const closeTrigger = event.target.closest('[data-nav-close]');
      if (closeTrigger) {
        event.preventDefault();
        closeDrawer();
        return;
      }

      const link = event.target.closest('a');
      if (!link) {
        return;
      }
      if (isDrawerMode() && document.body.classList.contains(bodyClass)) {
        closeDrawer({ returnFocus: false });
      }
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && document.body.classList.contains(bodyClass)) {
        closeDrawer();
      }
    });

    if (typeof mq.addEventListener === 'function') {
      mq.addEventListener('change', () => syncMode());
    } else if (typeof mq.addListener === 'function') {
      mq.addListener(() => syncMode());
    }

    syncMode();
  });
})();

