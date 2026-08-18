(function (global) {
  const API_BASE = global.API_BASE || "http://localhost:8000";

  function getToken() {
    return localStorage.getItem("whatsflow_token");
  }
  function setToken(t) {
    if (t) localStorage.setItem("whatsflow_token", t);
  }
  function clearAuth() {
    localStorage.removeItem("whatsflow_token");
    localStorage.removeItem("whatsflow_user");
  }

  async function request(path, opts) {
    opts = opts || {};
    const headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    const t = getToken();
    if (t) headers["Authorization"] = "Bearer " + t;
    const url = path.startsWith("http") ? path : API_BASE + path;
    let res;
    try {
      res = await fetch(url, {
        method: opts.method || "GET",
        headers: headers,
        body: opts.body ? JSON.stringify(opts.body) : undefined,
      });
    } catch (e) {
      throw new Error("Nao foi possivel conectar ao backend (" + API_BASE + "). Verifique se esta rodando.");
    }
    let data = null;
    try { data = await res.json(); } catch (e) {}
    if (!res.ok) {
      throw new Error((data && (data.detail || data.message)) || ("Erro HTTP " + res.status));
    }
    return data;
  }

  global.WFApi = {
    base: API_BASE,
    getToken: getToken,
    setToken: setToken,
    clearAuth: clearAuth,
    register: function (b) { return request("/api/auth/register", { method: "POST", body: b }); },
    login: function (b) { return request("/api/auth/login", { method: "POST", body: b }); },
    me: function () { return request("/api/auth/me"); },
    passwordResetRequest: function (b) { return request("/api/auth/password-reset/request", { method: "POST", body: b }); },
    listTemplates: function () { return request("/api/templates"); },
    importTemplate: function (slug) { return request("/api/templates/" + slug + "/import", { method: "POST" }); },
    listFlows: function () { return request("/api/flows"); },
    getFlow: function (id) { return request("/api/flows/" + id); },
    createFlow: function (b) { return request("/api/flows", { method: "POST", body: b }); },
    updateFlow: function (id, b) { return request("/api/flows/" + id, { method: "PUT", body: b }); },
    deleteFlow: function (id) { return request("/api/flows/" + id, { method: "DELETE" }); },
    simulateStart: function (id, b) { return request("/api/flows/" + id + "/simulate/start", { method: "POST", body: b || {} }); },
    simulateMessage: function (b) { return request("/api/flows/simulate/message", { method: "POST", body: b }); },
    listLeads: function (qs) { return request("/api/leads" + (qs || "")); },
    updateLead: function (id, b) { return request("/api/leads/" + id, { method: "PUT", body: b }); },
    deleteLead: function (id) { return request("/api/leads/" + id, { method: "DELETE" }); },
    listLeadNotes: function (leadId) { return request("/api/leads/" + leadId + "/notes"); },
    createLeadNote: function (leadId, b) { return request("/api/leads/" + leadId + "/notes", { method: "POST", body: b }); },
    deleteLeadNote: function (leadId, noteId) { return request("/api/leads/" + leadId + "/notes/" + noteId, { method: "DELETE" }); },
    exportLeadsUrl: function (qs) { return API_BASE + "/api/leads/export/csv" + (qs || ""); },
    metrics: function () { return request("/api/dashboard/metrics"); },
    getRoiSettings: function () { return request("/api/dashboard/roi-settings"); },
    updateRoiSettings: function (b) { return request("/api/dashboard/roi-settings", { method: "PUT", body: b }); },

    // ---- Inbox Humano (CRM 1.1) ----
    inboxList: function (qs) { return request("/api/inbox/conversations" + (qs || "")); },
    inboxGet: function (leadId) { return request("/api/inbox/conversations/" + leadId); },
    inboxAssume: function (leadId) { return request("/api/inbox/conversations/" + leadId + "/assume", { method: "POST" }); },
    inboxSend: function (leadId, b) { return request("/api/inbox/conversations/" + leadId + "/send", { method: "POST", body: b }); },
    inboxClose: function (leadId) { return request("/api/inbox/conversations/" + leadId + "/close", { method: "POST" }); },

    // ---- Agenda interna (Fase C.1) ----
    listAppointments: function (qs) { return request("/api/appointments" + (qs || "")); },
    createAppointment: function (b) { return request("/api/appointments", { method: "POST", body: b }); },
    updateAppointment: function (id, b) { return request("/api/appointments/" + id, { method: "PUT", body: b }); },
    deleteAppointment: function (id) { return request("/api/appointments/" + id, { method: "DELETE" }); },

    // ---- Planos ----
    listPlans: function () { return request("/api/plans"); },

    // ---- Admin ----
    adminOverview: function () { return request("/api/admin/overview"); },
    adminSystemHealth: function () { return request("/api/admin/system-health"); },
    adminBetaReadiness: function () { return request("/api/admin/beta-readiness"); },
    adminPlans: function () { return request("/api/admin/plans"); },
    adminUsers: function (qs) { return request("/api/admin/users" + (qs || "")); },
    adminUpdateUser: function (id, b) { return request("/api/admin/users/" + id, { method: "PUT", body: b }); },
    adminDeleteUser: function (id) { return request("/api/admin/users/" + id, { method: "DELETE" }); },
    adminPendingBilling: function (qs) { return request("/api/admin/pending-billing" + (qs || "")); },
    adminClaimPendingBilling: function (id, b) { return request("/api/admin/pending-billing/" + id + "/claim", { method: "POST", body: b || {} }); },
    adminIgnorePendingBilling: function (id) { return request("/api/admin/pending-billing/" + id + "/ignore", { method: "POST" }); },
    adminSubscriptions: function (qs) { return request("/api/admin/subscriptions" + (qs || "")); },
    adminBillingEvents: function (qs) { return request("/api/admin/billing-events" + (qs || "")); },

    // ---- CRM vertical (EMG-1A) ----
    crmBootstrapEmagrecentro: function () { return request("/api/crm/bootstrap/emagrecentro", { method: "POST" }); },
    crmTags: function () { return request("/api/crm/tags"); },
    crmCreateTag: function (b) { return request("/api/crm/tags", { method: "POST", body: b }); },
    crmUpdateTag: function (id, b) { return request("/api/crm/tags/" + id, { method: "PUT", body: b }); },
    crmDeleteTag: function (id) { return request("/api/crm/tags/" + id, { method: "DELETE" }); },
    crmCustomFields: function () { return request("/api/crm/custom-fields"); },
    crmCreateCustomField: function (b) { return request("/api/crm/custom-fields", { method: "POST", body: b }); },
    crmUpdateCustomField: function (id, b) { return request("/api/crm/custom-fields/" + id, { method: "PUT", body: b }); },
    crmDeleteCustomField: function (id) { return request("/api/crm/custom-fields/" + id, { method: "DELETE" }); },
    crmPipelines: function () { return request("/api/crm/pipelines"); },
    crmCreatePipeline: function (b) { return request("/api/crm/pipelines", { method: "POST", body: b }); },
    crmUpdatePipeline: function (id, b) { return request("/api/crm/pipelines/" + id, { method: "PUT", body: b }); },
    crmDeletePipeline: function (id) { return request("/api/crm/pipelines/" + id, { method: "DELETE" }); },
    crmCreateStage: function (pid, b) { return request("/api/crm/pipelines/" + pid + "/stages", { method: "POST", body: b }); },
    crmUpdateStage: function (id, b) { return request("/api/crm/pipeline-stages/" + id, { method: "PUT", body: b }); },
    crmDeleteStage: function (id) { return request("/api/crm/pipeline-stages/" + id, { method: "DELETE" }); },
    crmTasks: function (qs) { return request("/api/crm/tasks" + (qs || "")); },
    crmCreateTask: function (b) { return request("/api/crm/tasks", { method: "POST", body: b }); },
    crmUpdateTask: function (id, b) { return request("/api/crm/tasks/" + id, { method: "PUT", body: b }); },
    crmDeleteTask: function (id) { return request("/api/crm/tasks/" + id, { method: "DELETE" }); },
    crmQuickReplies: function () { return request("/api/crm/quick-replies"); },
    crmCreateQuickReply: function (b) { return request("/api/crm/quick-replies", { method: "POST", body: b }); },
    crmUpdateQuickReply: function (id, b) { return request("/api/crm/quick-replies/" + id, { method: "PUT", body: b }); },
    crmDeleteQuickReply: function (id) { return request("/api/crm/quick-replies/" + id, { method: "DELETE" }); },

    // ---- Setup / Nichos ----
    listNichePackages: function () { return request("/api/setup/niches"); },
    applyNichePackage: function (b) { return request("/api/setup/apply", { method: "POST", body: b }); },
    setupCreateFlow: function (b) { return request("/api/setup/create-flow", { method: "POST", body: b }); },
    setupCreateKb: function (b) { return request("/api/setup/create-kb", { method: "POST", body: b }); },
    setupIndexKb: function (b) { return request("/api/setup/index-kb", { method: "POST", body: b }); },

    // ---- Google Calendar ----
    calendarAuthUrl: function () { return request("/api/calendar/google/auth-url"); },
    calendarStatus: function () { return request("/api/calendar/status"); },
    calendarDisconnect: function () { return request("/api/calendar/disconnect", { method: "POST" }); },
    calendarSyncAppointment: function (id) { return request("/api/calendar/sync-appointment/" + id, { method: "POST" }); },

    // ---- WhatsApp Conexões (Fase 3) ----
    listConnections: function () { return request("/api/whatsapp/connections"); },
    createConnection: function (b) { return request("/api/whatsapp/connections", { method: "POST", body: b }); },
    deleteConnection: function (id) { return request("/api/whatsapp/connections/" + id, { method: "DELETE" }); },
    setConnectionAutomationPaused: function (id, paused) { return request("/api/whatsapp/connections/" + id + "/automation-paused", { method: "POST", body: { paused: !!paused } }); },
    sendTestMessage: function (id, b) { return request("/api/whatsapp/connections/" + id + "/send-test", { method: "POST", body: b }); },
    // Evolution / QR Code (Fase 5)
    createEvolutionConnection: function (b) { return request("/api/whatsapp/connections/evolution", { method: "POST", body: b }); },
    getEvolutionQrcode: function (id) { return request("/api/whatsapp/connections/" + id + "/qrcode"); },
    getEvolutionStatus: function (id) { return request("/api/whatsapp/connections/" + id + "/status"); },

    // ---- IA + RAG (Fase A) ----
    listKnowledgeBases: function () { return request("/api/ai/knowledge-bases"); },
    createKnowledgeBase: function (b) { return request("/api/ai/knowledge-bases", { method: "POST", body: b }); },
    deleteKnowledgeBase: function (id) { return request("/api/ai/knowledge-bases/" + id, { method: "DELETE" }); },
    indexKnowledge: function (id, b) { return request("/api/ai/knowledge-bases/" + id + "/index", { method: "POST", body: b }); },
    listKnowledgeChunks: function (id) { return request("/api/ai/knowledge-bases/" + id + "/chunks"); },
    deleteKnowledgeChunk: function (kbId, chunkId) { return request("/api/ai/knowledge-bases/" + kbId + "/chunks/" + chunkId, { method: "DELETE" }); },
    getAiSettings: function () { return request("/api/ai/settings"); },
    updateAiSettings: function (b) { return request("/api/ai/settings", { method: "PUT", body: b }); },
    aiAsk: function (b) { return request("/api/ai/ask", { method: "POST", body: b }); },
  };
})(window);
