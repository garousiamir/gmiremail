// Applies the saved theme before the page renders (no flash). Classic script: loaded in <head>.
try {
  const saved = localStorage.getItem('emk.theme');
  if (saved === 'light' || saved === 'dark') document.documentElement.dataset.theme = saved;
} catch { /* storage unavailable: follow the system */ }
