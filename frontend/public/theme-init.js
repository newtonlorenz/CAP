// Apply before paint. An external script also works with the production CSP.
(function () {
  var preference = 'system';
  try {
    preference = localStorage.getItem('cap:theme');
  } catch (_) { /* Follow the system when storage is unavailable. */ }
  var dark = preference === 'dark' || (preference !== 'light' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
  var theme = dark ? 'dark' : 'light';
  document.documentElement.dataset.theme = theme;
  document.documentElement.classList.toggle('dark', !!dark);
  document.documentElement.style.colorScheme = theme;
  document.querySelector('meta[name="theme-color"]').setAttribute('content', dark ? '#14171c' : '#f5f7fa');
}());
