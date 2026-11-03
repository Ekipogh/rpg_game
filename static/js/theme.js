/* Keep Tailwind and Bootstrap on the same theme before the page paints. */
(() => {
  const root = document.documentElement;
  const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
  let preference;
  try {
    preference = localStorage.getItem('theme');
  } catch (_) {
    // Theme switching still works when browser storage is unavailable.
  }

  function applyTheme(dark) {
    root.classList.toggle('dark', dark);
    root.dataset.bsTheme = dark ? 'dark' : 'light';
    root.style.colorScheme = dark ? 'dark' : 'light';
    const button = document.getElementById('theme-toggle');
    if (button) {
      button.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
      document.getElementById('theme-toggle-dark-icon')?.classList.toggle('hidden', dark);
      document.getElementById('theme-toggle-light-icon')?.classList.toggle('hidden', !dark);
    }
  }

  const useDark = () => preference === 'dark' ||
    (preference !== 'light' && systemTheme.matches);
  applyTheme(useDark());
  document.addEventListener('DOMContentLoaded', () => {
    applyTheme(useDark());
    document.getElementById('theme-toggle')?.addEventListener('click', () => {
      preference = root.classList.contains('dark') ? 'light' : 'dark';
      try {
        localStorage.setItem('theme', preference);
      } catch (_) {}
      applyTheme(useDark());
    });
  });
  systemTheme.addEventListener('change', () => applyTheme(useDark()));
  window.addEventListener('storage', (event) => {
    if (event.key === 'theme' || event.key === null) {
      preference = event.newValue;
      applyTheme(useDark());
    }
  });
})();
