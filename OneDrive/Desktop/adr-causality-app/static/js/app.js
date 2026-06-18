// ADR Causality Assessment System - Frontend JS

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = 'toast';
  const colors = { success: 'var(--accent-emerald)', error: 'var(--accent-rose)', info: 'var(--accent-sky)' };
  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  toast.innerHTML = `<div style="display:flex;align-items:center;gap:10px;">
    <span style="font-size:18px;">${icons[type] || icons.info}</span>
    <span style="font-size:13px;color:var(--text-primary);">${message}</span>
  </div>`;
  toast.style.borderLeft = `3px solid ${colors[type] || colors.info}`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Mobile sidebar toggle with overlay
document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');

  if (window.innerWidth <= 1024) {
    // Create hamburger toggle button
    const toggle = document.createElement('button');
    toggle.innerHTML = '☰';
    toggle.id = 'sidebarToggle';
    toggle.setAttribute('aria-label', 'Toggle menu');
    toggle.style.cssText = 'position:fixed;top:12px;left:12px;z-index:200;background:var(--bg-card);border:1px solid var(--border-color);color:var(--text-primary);padding:10px 14px;border-radius:8px;font-size:20px;cursor:pointer;min-width:44px;min-height:44px;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(0,0,0,0.3);';
    document.body.appendChild(toggle);

    function openSidebar() {
      sidebar.classList.add('open');
      if (overlay) overlay.classList.add('active');
    }

    function closeSidebar() {
      sidebar.classList.remove('open');
      if (overlay) overlay.classList.remove('active');
    }

    toggle.addEventListener('click', () => {
      if (sidebar.classList.contains('open')) {
        closeSidebar();
      } else {
        openSidebar();
      }
    });

    // Close sidebar when overlay is tapped
    if (overlay) {
      overlay.addEventListener('click', closeSidebar);
    }

    // Close sidebar when a nav link is clicked
    sidebar.querySelectorAll('.nav-link').forEach(link => {
      link.addEventListener('click', closeSidebar);
    });
  }
});
