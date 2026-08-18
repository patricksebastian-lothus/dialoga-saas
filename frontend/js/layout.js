(function (global) {
  const ICONS = {
    dashboard: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="7" height="8" rx="1.5"></rect><rect x="14" y="3" width="7" height="5" rx="1.5"></rect><rect x="14" y="12" width="7" height="9" rx="1.5"></rect><rect x="3" y="15" width="7" height="6" rx="1.5"></rect></svg>',
    setup: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19l5-1 9-9-4-4-9 9-1 5z"></path><path d="M13 6l4 4"></path><path d="M16 4l4 4"></path></svg>',
    leads: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="8" r="3"></circle><path d="M3.5 19c.8-3.2 2.8-5 5.5-5s4.7 1.8 5.5 5"></path><circle cx="17" cy="9" r="2.4"></circle><path d="M15.5 14.5c2.5.2 4.1 1.7 5 4.5"></path></svg>',
    etiquetas: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 13l-7 7-9-9V4h7l9 9z"></path><circle cx="8" cy="8" r="1.3"></circle></svg>',
    campos: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5" width="16" height="14" rx="2"></rect><path d="M8 9h8M8 13h5M8 17h8"></path></svg>',
    pipelines: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M7 12h10M10 18h4"></path></svg>',
    tarefas: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 11l2 2 4-4"></path><rect x="4" y="4" width="16" height="16" rx="2"></rect></svg>',
    respostas: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v10H8l-4 4V5z"></path><path d="M8 9h8M8 12h5"></path></svg>',
    inbox: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v10l-3 4H7l-3-4V5z"></path><path d="M4 15h5l1.5 2h3L15 15h5"></path></svg>',
    agenda: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"></rect><path d="M8 3v4M16 3v4M3 10h18"></path><path d="M8 14h3M8 17h6"></path></svg>',
    builder: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="6" cy="6" r="2.5"></circle><circle cx="18" cy="6" r="2.5"></circle><circle cx="12" cy="18" r="2.5"></circle><path d="M8.5 6h7M7.5 8l3.5 8M16.5 8L13 16"></path></svg>',
    ia: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l1.4 4.1L17.5 8.5l-4.1 1.4L12 14l-1.4-4.1-4.1-1.4 4.1-1.4L12 3z"></path><path d="M18 13l.8 2.2L21 16l-2.2.8L18 19l-.8-2.2L15 16l2.2-.8L18 13z"></path><path d="M6 14l.6 1.7L8.3 16.3l-1.7.6L6 18.6l-.6-1.7-1.7-.6 1.7-.6L6 14z"></path></svg>',
    planos: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"></rect><path d="M3 10h18"></path><path d="M7 15h4"></path></svg>',
    configuracoes: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3"></circle><path d="M19 12a7.8 7.8 0 0 0-.1-1l2-1.5-2-3.4-2.4 1a7 7 0 0 0-1.7-1L14.5 3h-5l-.3 3.1a7 7 0 0 0-1.7 1l-2.4-1-2 3.4 2 1.5a7.8 7.8 0 0 0 0 2l-2 1.5 2 3.4 2.4-1a7 7 0 0 0 1.7 1l.3 3.1h5l.3-3.1a7 7 0 0 0 1.7-1l2.4 1 2-3.4-2-1.5c.1-.3.1-.7.1-1z"></path></svg>',
    admin: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l7 3v5c0 4.6-2.8 8-7 10-4.2-2-7-5.4-7-10V6l7-3z"></path><path d="M9 12l2 2 4-5"></path></svg>'
  };

  const NAV_GROUPS = [
    { title: "Principal", items: [
      { id: "dashboard", label: "Dashboard", href: "dashboard.html" },
      { id: "setup", label: "Setup guiado", href: "setup.html" },
    ]},
    { title: "Atendimento", items: [
      { id: "inbox", label: "Conversas", href: "inbox.html" },
      { id: "agenda", label: "Agenda", href: "agenda.html" },
      { id: "respostas", label: "Respostas rápidas", href: "respostas-rapidas.html" },
    ]},
    { title: "Contatos & CRM", items: [
      { id: "leads", label: "Contatos", href: "leads.html" },
      { id: "etiquetas", label: "Etiquetas", href: "etiquetas.html" },
      { id: "campos", label: "Campos personalizados", href: "campos-personalizados.html" },
      { id: "pipelines", label: "Pipelines", href: "pipelines.html" },
      { id: "tarefas", label: "Tarefas", href: "tarefas.html" },
    ]},
    { title: "Automação", items: [
      { id: "builder", label: "Fluxos", href: "builder.html" },
      { id: "ia", label: "IA e conhecimento", href: "ia.html" },
    ]},
    { title: "Comercial", items: [
      { id: "planos", label: "Planos", href: "planos.html" },
    ]},
    { title: "Sistema", items: [
      { id: "configuracoes", label: "Configurações", href: "configuracoes.html" },
      { id: "admin", label: "Admin", href: "admin.html", adminOnly: true },
    ]},
  ];

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function renderSidebar(active) {
    const el = document.getElementById("app-sidebar");
    if (!el) return;

    let html = '' +
      '<div class="shell-brand"><img src="img/logo-dialoga.png" alt="dIAloga+"></div>' +
      '<nav class="shell-nav" aria-label="Navegação principal">';

    NAV_GROUPS.forEach(function (group) {
      html += '<div class="shell-group"><div class="shell-group-title">' + escapeHtml(group.title) + '</div>';
      group.items.forEach(function (item) {
        const attrs = item.adminOnly ? ' data-admin-only style="display:none"' : '';
        const icon = ICONS[item.id] || '';
        html += '<a class="shell-link ' + (active === item.id ? 'active' : '') + '" href="' + item.href + '"' + attrs + '>' +
          '<span class="shell-icon" aria-hidden="true">' + icon + '</span><span>' + escapeHtml(item.label) + '</span></a>';
      });
      html += '</div>';
    });

    html += '</nav>';
    el.innerHTML = html;
  }

  function renderTopbar(opts) {
    opts = opts || {};
    const titleEl = document.getElementById("app-topbar-title");
    if (titleEl) {
      titleEl.innerHTML = '<h1>' + escapeHtml(opts.title || "") + '</h1>' +
        (opts.subtitle ? '<p>' + escapeHtml(opts.subtitle) + '</p>' : '');
    }
    const actionsEl = document.getElementById("app-topbar-actions");
    if (actionsEl) actionsEl.innerHTML = opts.actionsHtml || "";
  }

  function render(opts) {
    opts = opts || {};
    renderSidebar(opts.active || "dashboard");
    renderTopbar(opts);
  }

  global.WFLayout = { render: render, renderSidebar: renderSidebar, renderTopbar: renderTopbar };
})(window);
