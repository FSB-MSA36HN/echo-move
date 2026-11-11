// Runtime configuration for the web UI.
// Point the UI at a remote backend (e.g. Colab + tunnel) with a query parameter:
//   index.html?server=https://xxxx.trycloudflare.com
//   index.html?server=wss://xxxx.trycloudflare.com/ws/pose
// The choice is remembered in localStorage; use ?server=local to reset.
(function () {
  const DEFAULT_HTTP = 'http://localhost:8000';
  let raw = new URLSearchParams(location.search).get('server');
  try {
    if (raw === 'local') { localStorage.removeItem('echo_server'); raw = null; }
    else if (raw) localStorage.setItem('echo_server', raw);
    else raw = localStorage.getItem('echo_server');
  } catch (e) { /* storage unavailable */ }

  let http = DEFAULT_HTTP;
  if (raw) {
    http = raw.replace(/^ws/, 'http').replace(/\/ws\/pose\/?$/, '').replace(/\/+$/, '');
    if (!/^https?:\/\//.test(http)) http = 'https://' + http;
  }
  window.ECHO_CONFIG = {
    apiBase: http,
    wsUrl: http.replace(/^http/, 'ws') + '/ws/pose',
  };
})();
