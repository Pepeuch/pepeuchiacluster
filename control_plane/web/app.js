/* Local UI only. Credentials stay in this closure; user content uses textContent. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const labels = {draft:"Brouillon",approved:"Approuvée",queued:"En attente",running:"En cours · simulation",completed:"Terminée · simulation",failed:"Échec simulé",cancel_requested:"Annulation demandée",cancelled:"Annulée",interrupted:"Interrompue"};
  const errors = {authentication_required:"Clé incorrecte ou session verrouillée.",access_denied:"Cette identité n’a pas accès à cette opération.",no_declared_capability:"Aucun worker de démonstration actif. Réenrôlez un worker avant de confier cette mission.",not_found:"Cette ressource n’est pas accessible.",version_conflict:"Une nouvelle version a été publiée. Actualisez puis vérifiez votre fichier avant de réessayer.",workspace_quota_exceeded:"Le quota de l’espace est atteint. Les anciennes versions sont conservées.",file_too_large:"Ce fichier dépasse la taille autorisée.",unsafe_file_name:"Utilisez un nom simple : lettres, chiffres, points et tirets, sans chemin ni nom réservé.",invalid_transition:"Cette action ne correspond plus à l’état de la mission. Actualisez la page.",operation_conflict:"Cette opération a déjà été utilisée avec un autre contenu.",invalid_text:"Indiquez un titre et un objectif dans les limites affichées.",object_corrupted:"L’intégrité du fichier n’a pas pu être vérifiée. Le téléchargement est refusé.",request_too_large:"Le téléversement dépasse la taille autorisée."};
  let credential = "", workspace = null, missions = [], files = null, selected = null, currentView = "dashboard", busy = false, refreshing = false;
  const pending = new Map(), selectedVersions = new Map();
  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text !== undefined && text !== null) element.textContent = String(text);
    if (className) element.className = className;
    return element;
  }
  function message(text) { $("notice").textContent = text; $("notice").hidden = !text; }
  async function request(path, {method="GET", data=null, binary=false}={}) {
    const response = await fetch(path, {method, credentials:"omit", cache:"no-store", headers:{Authorization:"Bearer " + credential, ...(data ? {"Content-Type":"application/json"} : {})}, body:data ? JSON.stringify(data) : undefined});
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      if (response.status === 401) lock();
      throw new Error(errors[body.error] || "Opération refusée. Vos données précédentes sont conservées.");
    }
    return binary ? response.blob() : response.json();
  }
  async function mutate(path, data) {
    const key = JSON.stringify([path, data]);
    if (!pending.has(key)) pending.set(key, crypto.randomUUID());
    while (pending.size > 8) pending.delete(pending.keys().next().value);
    const response = await request(path, {method:"POST", data:{...data, operation_id:pending.get(key)}});
    pending.delete(key);
    return response;
  }
  async function perform(action) {
    if (busy) return;
    busy = true; message("");
    document.querySelectorAll("button[type=submit]").forEach((button) => button.disabled = true);
    try { await action(); await refresh(); }
    catch (error) { message(error.message || "Le backend local est indisponible."); }
    finally { busy = false; document.querySelectorAll("button[type=submit]").forEach((button) => button.disabled = false); }
  }
  function lock() {
    credential = ""; workspace = null; missions = []; files = null; selected = null; pending.clear(); selectedVersions.clear();
    $("application").hidden = true; $("login").hidden = false; $("credential").value = "";
    $("mission-form").reset(); $("upload-form").reset();
    for (const id of ["mission-detail","mission-list","recent-missions","workspace-files","mission-inputs","active-mission","metrics"]) $(id).replaceChildren();
  }
  function navigate(view) {
    currentView = view;
    for (const name of ["dashboard","missions","workspaces"]) $(name + "-view").hidden = name !== view;
    document.querySelectorAll("[data-view]").forEach((button) => {
      if (button.dataset.view === view) button.setAttribute("aria-current", "page"); else button.removeAttribute("aria-current");
    });
  }
  function status(state) { return node("span", labels[state] || state, "status " + state); }
  function empty(target, title, text) { const box = node("div", null, "empty"); box.append(node("strong", title), node("span", text)); target.replaceChildren(box); }
  function missionRows(target, rows) {
    target.replaceChildren();
    if (!rows.length) return empty(target,"Aucune mission pour le moment.","Créez un brouillon puis choisissez explicitement de le confier au coordinateur simulé.");
    for (const mission of rows) {
      const row = node("div", null, "mission-row"), title = node("button", mission.title);
      title.type = "button"; title.addEventListener("click", () => { selected = mission.id; navigate("missions"); renderDetail().catch((error) => message(error.message)); });
      const info = node("div"); info.append(title, node("small", new Date(mission.created_at).toLocaleString("fr-FR")));
      row.append(info, status(mission.state)); target.append(row);
    }
  }
  function actionButton(label, action, quiet=false) {
    const button = node("button", label, quiet ? "quiet" : ""); button.type = "button";
    button.addEventListener("click", () => perform(action)); return button;
  }
  async function download(fileId, versionId, name) {
    const blob = await request(`/api/v1/workspaces/${workspace}/files/${fileId}/versions/${versionId}/download`, {binary:true});
    const url = URL.createObjectURL(blob), link = node("a"); link.href = url; link.download = name; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function renderDetail() {
    const target = $("mission-detail"), identity = selected;
    if (!identity) return empty(target,"Choisissez une mission.","Son objectif, son plan, ses états et ses livrables apparaîtront ici.");
    const mission = await request("/api/v1/missions/" + identity);
    const history = await request("/api/v1/missions/" + identity + "/events");
    if (selected !== identity || !credential) return;
    target.replaceChildren(node("p", "MISSION", "eyebrow"), node("h2", mission.title), status(mission.state), node("p", mission.id, "identity"), node("h3", "Objectif"), node("p", mission.objective, "objective"));
    const actions = node("div", null, "actions");
    if (mission.state === "draft") actions.append(actionButton("Confier au coordinateur simulé", async () => { if (confirm("Confirmer l’envoi de cette mission au coordinateur SIMULÉ ? Aucune IA réelle ne sera exécutée.")) await mutate(`/api/v1/missions/${identity}/approve`, {}); }));
    if (["draft","queued","running","interrupted"].includes(mission.state)) actions.append(actionButton("Demander l’annulation", async () => { if (confirm("Demander l’annulation de cette mission ?")) await mutate(`/api/v1/missions/${identity}/cancel`, {}); }, true));
    if (["failed","interrupted"].includes(mission.state)) actions.append(actionButton("Créer une nouvelle tentative", async () => { if (confirm("Autoriser explicitement une nouvelle tentative de simulation ?")) await mutate(`/api/v1/missions/${identity}/retry`, {}); }));
    target.append(actions);
    target.append(node("h3", "Versions de fichiers autorisées"));
    if (!mission.authorized_files.length) target.append(node("p", "Aucun fichier joint.", "hint"));
    for (const reference of mission.authorized_files) {
      const file = files?.files.find((item) => item.versions.some((version) => version.id === reference));
      const version = file?.versions.find((item) => item.id === reference);
      target.append(node("p", file ? `${file.name} · version ${version.number}` : "Version autorisée", "hint"), node("code", reference));
    }
    if (mission.state === "queued") target.append(node("p", "En attente du worker de démonstration, lancé manuellement.", "hint"));
    if (mission.state === "cancel_requested") target.append(node("p", "La demande est enregistrée. L’arrêt sera confirmé par le worker ou la tentative sera interrompue à expiration.", "hint"));
    if (mission.plan) {
      target.append(node("h3", "Plan du coordinateur · SIMULATION"));
      const description = node("dl");
      for (const [label,value] of [["Rôle demandé",mission.plan.role],["Capacité déclarée",mission.plan.capability],["Worker sélectionné",mission.plan.worker_id],["Exécution vérifiée",mission.state === "completed" ? "Démonstration déterministe uniquement" : "Pas de résultat validé"]]) description.append(node("dt", label), node("dd", value));
      target.append(description);
    }
    target.append(node("h3", "Livrables"));
    if (!mission.results.length) target.append(node("p", "Aucun livrable durable validé pour cette mission.", "hint"));
    for (const result of mission.results) target.append(actionButton("Télécharger resultat.md", () => download(result.file_id, result.version_id, "resultat.md"), true));
    if (mission.attempts.length) {
      target.append(node("h3", "Tentatives"));
      for (const attempt of mission.attempts) target.append(node("p", `#${attempt.number} · ${labels[attempt.state] || attempt.state}${attempt.error_code ? " · " + attempt.error_code : ""}`, "hint"), node("code", attempt.id));
    }
    target.append(node("h3", "Historique"));
    for (const event of history.events) {
      const row = node("div", null, "event"), info = node("div");
      const description = event.details.state ? `${labels[event.details.state]} · ${event.details.state}` : event.type === "file_published" ? "Fichier durable publié" : event.type === "attempt_started" ? "Tentative attribuée au worker simulé" : event.type;
      info.append(node("span", description), node("small", event.actor));
      row.append(node("time", new Date(event.at).toLocaleTimeString("fr-FR")), info); target.append(row);
    }
  }
  function renderFiles() {
    const target = $("workspace-files"); target.replaceChildren();
    $("quota").textContent = `${files.used_bytes.toLocaleString("fr-FR")} / ${files.quota_bytes.toLocaleString("fr-FR")} octets · maximum ${files.max_file_bytes.toLocaleString("fr-FR")} octets par fichier`;
    if (!files.files.length) empty(target,"Votre espace est vide.","Téléversez un fichier ou terminez une simulation pour obtenir un premier livrable.");
    for (const file of files.files) {
      const card = node("article", null, "card file-card"), info = node("div"), versions = node("select");
      versions.setAttribute("aria-label", "Version de " + file.name);
      for (const version of file.versions) { const option = node("option", `Version ${version.number} · ${version.size} octets`); option.value = version.id; versions.append(option); }
      versions.value = selectedVersions.get(file.id) || file.current_version;
      const description = node("p"), checksum = node("code");
      function describe() { const version = file.versions.find((item) => item.id === versions.value); description.textContent = version.mission_id ? "Livrable de mission · " + version.mission_id : "Fichier téléversé"; checksum.textContent = "SHA256 · " + version.sha256; }
      versions.addEventListener("change", () => { selectedVersions.set(file.id, versions.value); describe(); });
      describe(); info.append(node("h2", file.name), description, checksum);
      card.append(info, versions, actionButton("Télécharger", () => download(file.id, versions.value, file.name), true)); target.append(card);
    }
    const selectedInputs = new Set(Array.from($("mission-inputs").selectedOptions, (option) => option.value));
    $("mission-inputs").replaceChildren();
    for (const file of files.files) { const option = node("option", file.name + " · dernière version"); option.value = file.current_version; option.selected = selectedInputs.has(option.value); $("mission-inputs").append(option); }
  }
  async function refresh() {
    if (!credential || refreshing) return;
    refreshing = true;
    try {
      const [dashboard, listing, fileListing] = await Promise.all([request("/api/v1/dashboard"),request("/api/v1/missions"),request(`/api/v1/workspaces/${workspace}/files`)]);
      if (!credential) return;
      missions = listing.missions; files = fileListing;
      $("connection").textContent = "Backend local connecté";
      $("metrics").replaceChildren();
      for (const [label,value,hint] of [["Missions",dashboard.mission_count,"brouillons inclus"],["Tâches en attente",dashboard.queued_tasks,"approbation enregistrée"],["Tâches terminées",dashboard.completed_tasks,"livrables persistants"]]) { const metric = node("div", null, "metric"); metric.append(node("span",label,"metric-label"),node("strong",value),node("span",hint)); $("metrics").append(metric); }
      if (dashboard.active_mission) { $("active-mission").replaceChildren(node("p",dashboard.active_mission.title),status(dashboard.active_mission.state)); } else empty($("active-mission"),"Aucune mission en cours.","Les brouillons restent en attente de votre décision.");
      const worker = dashboard.nodes.find((item) => item.status === "active") || dashboard.nodes[0]; $("worker-state").replaceChildren(node("p",worker.id),node("p",worker.state === "revoked" ? "Worker révoqué · aucun travail autorisé." : worker.state === "simulated_busy" ? "Une tentative de simulation est active." : "Démarrage manuel · aucune présence en ligne déduite."),node("p",`${worker.verified_simulated_executions} simulation(s) publiée(s) · matériel non validé`,"hint"));
      missionRows($("recent-missions"), missions.slice(0, 5)); missionRows($("mission-list"), missions); renderFiles(); await renderDetail();
    } catch (error) { $("connection").textContent = "Backend indisponible"; message(error.message || "Connexion interrompue. Vos données restent conservées."); }
    finally { refreshing = false; }
  }
  $("login-form").addEventListener("submit", async (event) => {
    event.preventDefault(); credential = $("credential").value; $("credential").value = ""; $("login-error").textContent = "";
    try { await request("/api/v1/health"); const listing = await request("/api/v1/workspaces"); workspace = listing.workspaces[0].id; $("login").hidden = true; $("application").hidden = false; navigate("dashboard"); await refresh(); }
    catch (error) { credential = ""; $("login-error").textContent = error.message || "Impossible de joindre le backend local."; }
  });
  $("logout").addEventListener("click", lock);
  document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => navigate(button.dataset.view)));
  for (const id of ["new-mission","all-missions"]) $(id).addEventListener("click", () => { navigate("missions"); $("mission-title").focus(); });
  $("mission-form").addEventListener("submit", (event) => { event.preventDefault(); perform(async () => {
    const mission = await mutate("/api/v1/missions", {workspace_id:workspace,title:$("mission-title").value,objective:$("mission-objective").value,authorized_files:Array.from($("mission-inputs").selectedOptions, (option) => option.value)});
    selected = mission.id; $("mission-form").reset();
  }); });
  $("upload-file").addEventListener("change", () => { $("upload-name").value = $("upload-file").files[0]?.name || ""; });
  $("upload-form").addEventListener("submit", (event) => { event.preventDefault(); perform(async () => {
    const file = $("upload-file").files[0], name = $("upload-name").value;
    if (!file) return;
    if (file.size > files.max_file_bytes) throw new Error(errors.file_too_large);
    const bytes = new Uint8Array(await file.arrayBuffer());
    const checksum = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), (byte) => byte.toString(16).padStart(2,"0")).join("");
    const chunks = []; for (let i=0; i<bytes.length; i+=8192) chunks.push(String.fromCharCode(...bytes.subarray(i,i+8192)));
    const previous = files.files.find((item) => item.name.toLowerCase() === name.toLowerCase());
    await mutate(`/api/v1/workspaces/${workspace}/files`, {name,content_base64:btoa(chunks.join("")),size:bytes.length,sha256:checksum,expected_version:previous?.current_version || null});
    $("upload-form").reset();
  }); });
  setInterval(() => { if (credential) refresh(); }, 2000);
  navigate(currentView);
})();
