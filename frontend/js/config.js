(function (global) {
  // Configuração pública do frontend.
  // Em produção com domínio próprio, altere este arquivo uma vez em vez de editar todos os HTMLs.
  const DEFAULT_API_BASE = "https://dialoga-backend-r1zp.onrender.com";
  const DEFAULT_FRONTEND_BASE = "https://dialoga-frontend-wird.onrender.com";

  global.API_BASE = global.API_BASE || DEFAULT_API_BASE;
  global.WF_PUBLIC_CONFIG = Object.assign({}, global.WF_PUBLIC_CONFIG || {}, {
    apiBase: global.API_BASE,
    frontendBase: DEFAULT_FRONTEND_BASE,
    privacyUrl: DEFAULT_FRONTEND_BASE + "/privacidade.html",
    termsUrl: DEFAULT_FRONTEND_BASE + "/termos.html",
  });
})(window);
