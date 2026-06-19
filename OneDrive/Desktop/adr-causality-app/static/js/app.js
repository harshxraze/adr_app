// ADR Causality Assessment System - Frontend JS

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = 'toast-anim bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-4 shadow-xl mb-3 min-w-[280px] max-w-[360px]';
  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  const borderColors = { success: 'border-l-emerald-500', error: 'border-l-rose-500', info: 'border-l-sky-500' };
  toast.classList.add('border-l-4', borderColors[type] || borderColors.info);
  toast.innerHTML = `<div class="flex items-center gap-3">
    <span class="text-lg">${icons[type] || icons.info}</span>
    <span class="text-sm text-gray-800 dark:text-gray-200">${message}</span>
  </div>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ===== Theme Toggle =====
function initTheme() {
  const saved = localStorage.getItem('adr-theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const isDark = saved ? saved === 'dark' : prefersDark;
  document.documentElement.classList.toggle('dark', isDark);
  updateThemeUI(isDark);
}

function toggleTheme() {
  const isDark = document.documentElement.classList.toggle('dark');
  localStorage.setItem('adr-theme', isDark ? 'dark' : 'light');
  updateThemeUI(isDark);
}

function updateThemeUI(isDark) {
  const icon = isDark ? '☀️' : '🌙';
  const label = isDark ? 'Light Mode' : 'Dark Mode';
  const el = document.getElementById('themeIcon');
  const lbl = document.getElementById('themeLabel');
  const mob = document.getElementById('themeIconMobile');
  if (el) el.textContent = icon;
  if (lbl) lbl.textContent = label;
  if (mob) mob.textContent = icon;
}

// ===== Sidebar Toggle =====
document.addEventListener('DOMContentLoaded', () => {
  initTheme();

  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  const toggle = document.getElementById('sidebarToggle');
  const themeBtn = document.getElementById('themeToggle');
  const themeBtnMobile = document.getElementById('themeToggleMobile');

  function openSidebar() {
    sidebar.classList.remove('-translate-x-full');
    sidebar.classList.add('translate-x-0');
    overlay.classList.remove('hidden');
  }

  function closeSidebar() {
    sidebar.classList.add('-translate-x-full');
    sidebar.classList.remove('translate-x-0');
    overlay.classList.add('hidden');
  }

  if (toggle) {
    toggle.addEventListener('click', () => {
      if (sidebar.classList.contains('-translate-x-full')) {
        openSidebar();
      } else {
        closeSidebar();
      }
    });
  }

  if (overlay) overlay.addEventListener('click', closeSidebar);

  // Close sidebar on nav link click (mobile)
  sidebar.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => {
      if (window.innerWidth < 1024) closeSidebar();
    });
  });

  // Theme buttons
  if (themeBtn) themeBtn.addEventListener('click', toggleTheme);
  if (themeBtnMobile) themeBtnMobile.addEventListener('click', toggleTheme);
});
