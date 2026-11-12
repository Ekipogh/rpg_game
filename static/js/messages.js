/* Shared dismissal for page feedback, including alerts added by Unicorn. */
(() => {
  const selector = '.message-overlay .alert';
  const scheduled = new WeakSet();

  window.closeMessageAlert = function () {
    document.querySelectorAll(selector).forEach(alert => alert.remove());
  };

  function scheduleAlerts() {
    document.querySelectorAll(selector).forEach(alert => {
      if (scheduled.has(alert)) return;
      scheduled.add(alert);
      window.setTimeout(() => alert.remove(), 3000);
    });
  }

  scheduleAlerts();
  new MutationObserver(scheduleAlerts).observe(document.body, {
    childList: true,
    subtree: true,
  });
})();
