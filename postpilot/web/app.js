/* SOCIA AI — interface : comptes, tâches, fenêtres, journal (polling 2 s). */
"use strict";

const $ = (s) => document.querySelector(s);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};
const PLATFORMS = {
  facebook: "Facebook",
  instagram: "Instagram",
  tiktok: "TikTok",
};
const HOME_URL = {
  facebook: "https://www.facebook.com/",
  instagram: "https://www.instagram.com/",
  tiktok: "https://www.tiktok.com/",
};

async function api(path, body) {
  const opts = body
    ? {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    : {};
  const r = await fetch(path, opts);
  return r.json();
}

function show(node, text, ok) {
  node.textContent = text;
  node.classList.remove("hidden", "ok", "err");
  node.classList.add(ok ? "ok" : "err");
  setTimeout(() => node.classList.add("hidden"), 6000);
}

/* ── Comptes ─────────────────────────────────────────────── */
let _accountsKey = "";
function renderAccounts(accounts, platforms) {
  const key = JSON.stringify([accounts, platforms]);
  if (key === _accountsKey) return;      // ne pas écraser la saisie en cours
  const box = $("#accounts");
  box.innerHTML = "";
  _accountsKey = key;
  for (const p of platforms) {
    const acc = accounts.find((a) => a.platform === p.id) || null;
    const status = acc ? acc.status : "none";
    const card = el("div", "acc");

    const head = el("div", "head");
    const dot = el("span", "dot " + (status === "connected" ? "ok" : status === "error" ? "err" : status === "pending" ? "pending" : ""));
    head.appendChild(dot);
    head.appendChild(el("span", "name", p.label));
    card.appendChild(head);

    const statusLine = el("div", "status",
      status === "connected"
        ? "✔ Prêt à publier" + (acc && acc.label ? " — " + acc.label : "")
        : status === "error"
        ? "✖ Échec de la dernière publication — vérifiez la fenêtre du réseau"
        : status === "pending"
        ? "• Fenêtre ouverte — connectez-vous-y vous-même, la session sera gardée"
        : "• Cliquez sur « Ouvrir la fenêtre » puis connectez-y vous-même");
    card.appendChild(statusLine);

    const row = el("div", "row");

    const bSave = el("button", "small primary", "Ouvrir la fenêtre");
    bSave.onclick = async () => {
      const res = await api("/api/accounts", {
        platform: p.id,
        // plus de champ URL : on ouvre sur le réseau (profil déjà enregistré
        // s'il y en a un, sinon la page d'accueil du réseau)
        profile_url: (acc && acc.profile_url) || HOME_URL[p.id] || "",
      });
      show(statusLine, res.message, res.ok);
      setTimeout(refresh, 1500);
    };

    const bVerify = el("button", "small", "Vérifier la session");
    bVerify.onclick = async () => {
      statusLine.textContent = "Vérification en cours…";
      const res = await api("/api/accounts/verify", { platform: p.id });
      show(statusLine, res.message, res.ok);
      refresh();
    };

    const bForget = el("button", "small danger", "Oublier");
    bForget.onclick = async () => {
      await api("/api/accounts/forget", { platform: p.id });
      refresh();
    };

    row.append(bSave, bVerify, bForget);
    card.appendChild(row);

    // ── Gestionnaire de liens (pages & groupes) : + / flèche / X ──
    if (p.id === "facebook") buildLinksBlock(card);

    box.appendChild(card);
  }
}

/* ── Liens enregistrés (pages & groupes) : + / flèche ▾ / X ── */
let _links = [];
let _linksKey = "";
let _linksOpen = false;
let _linkDraft = "";
let _linksBox = null;

function setLinks(links) {
  _links = links || [];
  _linksKey = JSON.stringify(_links);
  if (_linksBox) paintLinks();
}

function renderLinks(links) {
  const key = JSON.stringify(links || []);
  if (key === _linksKey) return;        // rien n'a changé : on ne repeint pas
  setLinks(links);
}

function linkMsg(text, ok) {
  const n = _linksBox && _linksBox.querySelector(".link-msg");
  if (!n) return;
  n.textContent = text;
  n.classList.remove("hidden", "ok", "err");
  n.classList.add(ok ? "ok" : "err");
  clearTimeout(n._t);
  n._t = setTimeout(() => n.classList.add("hidden"), 6000);
}

function buildLinksBlock(card) {
  const block = el("div", "links-block");

  const head = el("div", "links-head");
  head.appendChild(el("span", "links-title", "Liens enregistrés (pages & groupes)"));
  head.appendChild(el("span", "links-count", ""));
  block.appendChild(head);

  const row = el("div", "link-row");
  const input = el("input", "link-input");
  input.type = "text";
  input.placeholder = "https://www.facebook.com/groups/…";
  input.value = _linkDraft;
  input.addEventListener("input", () => { _linkDraft = input.value; });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); addLink(); }
  });
  const bAdd = el("button", "primary small link-add", "+");
  bAdd.title = "Ajouter ce lien à la base";
  bAdd.onclick = addLink;
  const bToggle = el("button", "small links-toggle", "▾");
  bToggle.title = "Afficher la liste des liens enregistrés";
  bToggle.onclick = () => { _linksOpen = !_linksOpen; paintLinks(); };
  row.append(input, bAdd, bToggle);
  block.appendChild(row);

  block.appendChild(el("div", "msg link-msg hidden"));

  // ── Import d'un fichier Excel CHOISI par l'utilisateur (bouton +) ──
  const xlsRow = el("div", "import-row");
  const bXlsx = el("button", "small link-import", "+ Fichier Excel");
  bXlsx.title = "Importer les liens d'un fichier Excel (.xlsx) que vous " +
                "choisissez — doublons ignorés, sans limite de nombre";
  const filePick = el("input");
  filePick.type = "file";
  filePick.accept = ".xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  filePick.classList.add("hidden");
  filePick.onchange = () => {
    const f = filePick.files && filePick.files[0];
    filePick.value = "";              // on peut re-sélectionner le même fichier
    if (f) importLinksFile(f, bXlsx);
  };
  bXlsx.onclick = () => filePick.click();
  xlsRow.append(bXlsx, filePick);
  block.appendChild(xlsRow);

  const list = el("div", "link-list hidden");
  const lhead = el("div", "link-list-head");
  const bAll = el("button", "small link-all", "Tout cocher");
  bAll.onclick = () => selectIds(_links.map((l) => l.id));
  const bNone = el("button", "small link-none", "Tout décocher");
  bNone.onclick = () => selectIds([]);
  lhead.append(bAll, bNone);
  list.appendChild(lhead);
  list.appendChild(el("div", "link-rows"));
  block.appendChild(list);

  card.appendChild(block);
  _linksBox = block;
  paintLinks();
}

function paintLinks() {
  const box = _linksBox;
  if (!box) return;
  const selected = _links.filter((l) => l.selected);

  box.querySelector(".links-count").textContent =
    `${_links.length} lien(s) · ${selected.length} coché(s)`;
  const tg = box.querySelector(".links-toggle");
  tg.textContent = `▾ ${selected.length}/${_links.length}`;
  tg.classList.toggle("on", _linksOpen);
  box.querySelector(".link-list").classList.toggle("hidden", !_linksOpen);

  const rows = box.querySelector(".link-rows");
  rows.innerHTML = "";
  if (!_links.length) {
    rows.appendChild(el("p", "hint",
      "Aucun lien pour l'instant — ajoutez un lien avec le bouton +."));
  }
  for (const l of _links) {
    const item = el("div", "link-item");

    const lab = el("label", "link-label");
    const cb = el("input");
    cb.type = "checkbox";
    cb.checked = !!l.selected;
    cb.onchange = () => {
      const ids = [];
      for (const x of _links) {
        if (x.id === l.id ? cb.checked : x.selected) ids.push(x.id);
      }
      selectIds(ids);
    };
    const url = el("span", "url", l.url);
    url.title = l.url;
    lab.append(cb, url);
    item.appendChild(lab);

    const bX = el("button", "small danger link-x", "X");
    bX.title = "Supprimer ce lien de la liste";
    bX.onclick = async () => {
      try {
        const res = await api("/api/links/delete", { id: l.id });
        if (res && res.ok) {
          setLinks(res.links || []);
          linkMsg(res.message, true);
        } else {
          linkMsg((res && res.message) || "Suppression impossible", false);
        }
      } catch (e) {
        linkMsg("Serveur injoignable", false);
      }
    };
    item.appendChild(bX);
    rows.appendChild(item);
  }
}

/* ── Import d'un fichier Excel choisi par l'utilisateur ── */
async function importLinksFile(file, btn) {
  if (!file) return;
  if (btn) btn.disabled = true;
  linkMsg("Lecture du fichier « " + file.name + " »…", true);
  try {
    const r = await fetch("/api/links/import-file", {
      method: "POST",
      headers: { "X-File-Name": encodeURIComponent(file.name) },
      body: file,
    });
    const j = await r.json();
    linkMsg(j.message || (j.ok ? "Fichier importé" : "Import impossible"),
            !!j.ok);
    if (j.ok) {
      _linksOpen = true;               // on montre la liste nourrie
      setLinks(j.links || []);
      refresh();
    }
  } catch (e) {
    linkMsg("Serveur injoignable", false);
  }
  if (btn) btn.disabled = false;
}

async function selectIds(ids) {
  // mise à jour immédiate (réactivité), puis confirmation au serveur
  const want = new Set(ids);
  setLinks(_links.map((x) => ({ ...x, selected: want.has(x.id) })));
  try {
    const res = await api("/api/links/select", { ids: ids });
    if (res && res.ok) {
      setLinks(res.links || []);
    } else {
      linkMsg((res && res.message) || "Sélection impossible", false);
    }
  } catch (e) {
    linkMsg("Serveur injoignable", false);
  }
}

async function addLink() {
  const input = _linksBox && _linksBox.querySelector(".link-input");
  const url = (input ? input.value : _linkDraft).trim();
  if (!url) {
    linkMsg("Entrez d'abord un lien (page ou groupe Facebook).", false);
    return;
  }
  try {
    const res = await api("/api/links", { platform: "facebook", url: url });
    if (res && res.ok) {
      _linkDraft = "";
      if (input) input.value = "";
      _linksOpen = true;              // on montre la liste nouvellement nourrie
      setLinks(res.links || []);
      linkMsg(res.message, true);
    } else {
      linkMsg((res && res.message) || "Ajout impossible", false);
    }
  } catch (e) {
    linkMsg("Serveur injoignable", false);
  }
}

/* ── Tâches ──────────────────────────────────────────────── */
function renderTasks(tasks) {
  const box = $("#tasks");
  if (_editForm && !(tasks || []).some((t) => t.id === _editTaskId)) {
    _closeEditForm();     // la tâche éditée n'existe plus : on referme
  }
  box.innerHTML = "";
  if (!tasks.length) {
    box.appendChild(el("p", "hint", "Aucune tâche pour l'instant."));
    return;
  }
  for (const t of tasks) {
    const row = el("div", "task");
    const info = el("div", "info");
    info.appendChild(el("div", "sum", t.summary || t.content || "(tâche)"));
    const meta = el("div", "meta");
    const period = formatPeriod(t);
    const prog = (t.progress && t.progress.total)
      ? ` · progression ${t.progress.done || 0}/${t.progress.total}` : "";
    meta.textContent =
      `${PLATFORMS[t.platform] || t.platform} · ${
        KIND_LABELS[t.kind] || "Post"} · ` +
      `${t.enabled ? "prochaine " + (t.next_run || "") : "en pause"} · ` +
      `exécutée ${t.runs || 0} fois` +
      prog +
      ((t.photos && t.photos.length)
        ? ` · 📸 ${t.photos.length} photo(s) Gemini` : "") +
      (period ? ` · ${period}` : "");
    info.appendChild(meta);
    if (t.last_status) {
      const st = el(
        "div",
        String(t.last_status).startsWith("ok") ? "state-ok" : "state-err",
        "dernier résultat : " + t.last_status
      );
      info.appendChild(st);
    }
    row.appendChild(info);

    const actions = el("div", "actions");
    const bRun = el("button", "small primary", "Lancer maintenant");
    bRun.onclick = async () => {
      bRun.disabled = true;
      const res = await api("/api/tasks/run", { id: t.id });
      bRun.disabled = false;
      flashJournal();
      alert(res.message);
    };
    const bEdit = el("button", "small", "Modifier");
    bEdit.onclick = () => toggleEditForm(row, t);
    const bPause = el("button", "small", t.enabled ? "Pause" : "Reprendre");
    bPause.onclick = async () => {
      bPause.disabled = true;
      const res = await api("/api/tasks/toggle", { id: t.id });
      bPause.disabled = false;
      if (res && res.message) flashMsg(res.message, res.ok);
      refresh();
    };
    const bDel = el("button", "small danger", "Supprimer");
    bDel.onclick = async () => {
      if (!confirm("Supprimer cette tâche ? Le travail en cours sera arrêté.")) return;
      bDel.disabled = true;
      await api("/api/tasks/delete", { id: t.id });
      refresh();
    };
    actions.append(bRun, bEdit, bPause, bDel);
    row.appendChild(actions);
    box.appendChild(row);
    // le formulaire de modification SURVIT aux rafraîchissements (2 s) :
    // détaché du DOM, il est rattaché à sa ligne à chaque repeint
    if (_editForm && _editTaskId === t.id) row.appendChild(_editForm);
  }
}

/* ── Modifier une tâche existante (même lancée) ───────── */
let _editForm = null;      // formulaire « vivant » (survit au repeint 2 s)
let _editTaskId = null;

function _closeEditForm() {
  if (_editForm) _editForm.remove();
  _editForm = null;
  _editTaskId = null;
}

function toggleEditForm(row, t) {
  if (_editForm && _editTaskId === t.id) { _closeEditForm(); return; }
  _closeEditForm();
  const form = el("div", "edit-form");
  const ta = el("textarea", "edit-content");
  ta.rows = 2;
  ta.value = t.content || "";
  ta.placeholder = "Texte à publier";
  form.appendChild(ta);
  const line = el("div", "edit-line");
  const labFr = el("label", "", "Toutes les ");
  const inpFr = el("input", "edit-freq");
  inpFr.type = "number"; inpFr.min = "1"; inpFr.max = "1440";
  inpFr.value = t.interval_seconds ? Math.round(t.interval_seconds / 60) : "";
  inpFr.placeholder = "min";
  inpFr.title = "Fréquence en minutes (1 à 1440)";
  labFr.appendChild(inpFr);
  labFr.appendChild(document.createTextNode(" min"));
  const labMedia = el("label", "", "Média : ");
  const inpMedia = el("input", "edit-media");
  inpMedia.type = "text";
  inpMedia.value = t.media || "";
  inpMedia.placeholder = "nom du fichier (optionnel)";
  labMedia.appendChild(inpMedia);
  line.append(labFr, labMedia);
  form.appendChild(line);
  const line1b = el("div", "edit-line");
  const labQ = el("label", "", "Liens/exécution : ");
  const selQ = el("select", "edit-quota");
  [[0, "tous"], [5, "5"], [10, "10"], [20, "20"], [50, "50"]].forEach(
    ([v, txt]) => {
      const o = el("option", "", txt);
      o.value = String(v);
      selQ.appendChild(o);
    });
  selQ.value = String(t.max_targets || 0);
  labQ.appendChild(selQ);
  const labP = el("label", "check-inline");
  const cbP = el("input");
  cbP.type = "checkbox";
  cbP.checked = !!t.pretty_photo;
  labP.append(cbP, document.createTextNode(" photo présentable"));
  line1b.append(labQ, labP);
  form.appendChild(line1b);
  const line2 = el("div", "edit-line");
  const labS = el("label", "", "Début : ");
  const inpS = el("input", "edit-start");
  inpS.type = "datetime-local";
  inpS.value = (t.start_at || "").slice(0, 16);
  labS.appendChild(inpS);
  const labE = el("label", "", "Fin : ");
  const inpE = el("input", "edit-end");
  inpE.type = "datetime-local";
  inpE.value = (t.end_at || "").slice(0, 16);
  labE.appendChild(inpE);
  line2.append(labS, labE);
  form.appendChild(line2);
  const btns = el("div", "edit-btns");
  const bSave = el("button", "small primary", "Enregistrer");
  bSave.onclick = async () => {
    bSave.disabled = true;
    const res = await api("/api/tasks/update", {
      id: t.id,
      content: ta.value,
      interval_minutes: inpFr.value,
      media: inpMedia.value,
      start_at: inpS.value,
      end_at: inpE.value,
      max_targets: Number(selQ.value) || 0,
      pretty_photo: cbP.checked,
    });
    bSave.disabled = false;
    flashMsg(res.message, res.ok);
    if (res && res.ok) _closeEditForm();
    refresh();
  };
  const bCancel = el("button", "small", "Annuler");
  bCancel.onclick = () => _closeEditForm();
  btns.append(bSave, bCancel);
  form.appendChild(btns);
  _editForm = form;
  _editTaskId = t.id;
  row.appendChild(form);
}

function flashMsg(text, ok) {
  const box = $("#task-msg");
  if (box) show(box, text, !!ok);
  box.classList.remove("hidden");
  box.scrollIntoView({ block: "nearest" });
}

/* ── En direct des fenêtres (aperçu intégré) ─────────────── */
const LIVE_PLATFORMS = ["facebook", "instagram", "tiktok"];
const KIND_LABELS = { story: "Story", video: "Vidéo", post: "Post" };

function buildLive() {
  const box = $("#live");
  box.innerHTML = "";
  for (const p of LIVE_PLATFORMS) {
    const s = el("div", "screen");
    s.dataset.platform = p;

    const head = el("div", "screen-head");
    const dot = el("span", "dot");
    head.appendChild(dot);
    head.appendChild(el("b", "name", PLATFORMS[p]));
    head.appendChild(el("span", "state", "fermée"));
    const btn = el("button", "small", "Ouvrir");
    head.appendChild(btn);
    // seconde action : ouvrir VISIBLE (pour se connecter soi-même)
    const btnVis = el("button", "small", "Visible");
    btnVis.title = "Ouvrir la fenêtre visible à l'écran (connexion)";
    btnVis.onclick = async () => {
      btnVis.disabled = true;
      await api("/api/window/open", { platform: p, visible: true });
      btnVis.disabled = false;
      refresh();
    };
    head.appendChild(btnVis);
    s.appendChild(head);

    s.appendChild(el("div", "screen-url", ""));

    const body = el("div", "screen-body");
    const img = document.createElement("img");
    img.alt = "";
    img.style.display = "none";
    const off = el("div", "screen-off", "Fenêtre fermée — cliquez sur « Ouvrir »");
    body.append(img, off);
    s.appendChild(body);
    box.appendChild(s);
  }
}

function renderLive(windows) {
  if (!$("#live").children.length) buildLive();
  const open = new Map((windows || []).map((w) => [w.platform, w]));
  for (const s of document.querySelectorAll(".screen")) {
    const p = s.dataset.platform;
    const w = open.get(p);
    const state = s.querySelector(".state");
    const dot = s.querySelector(".dot");
    const url = s.querySelector(".screen-url");
    const btn = s.querySelector("button");
    const btnVis = s.querySelectorAll("button")[1];
    if (w) {
      state.textContent = w.visible
        ? `${w.pages} onglet(s) · visible`
        : `${w.pages} onglet(s) · arrière-plan`;
      dot.classList.add("ok");
      url.textContent = (w.urls && w.urls[0]) || "";
      btn.textContent = "Fermer";
      btn.onclick = async () => {
        // on marque « fermée » tout de suite : plus d'aperçu demandé à tort
        state.textContent = "fermée";
        await api("/api/window/close", { platform: p });
        refresh();
      };
    } else {
      state.textContent = "fermée";
      dot.classList.remove("ok");
      url.textContent = "";
      btn.textContent = "Ouvrir";
      btn.onclick = async () => {
        state.textContent = "ouverture…";
        // en arrière-plan : pas de pop-up, tout se suit dans l'aperçu
        await api("/api/window/open", { platform: p });
        refresh();
      };
      // fenêtre fermée : on efface l'image périmée et on remet le message
      const img = s.querySelector("img");
      const off = s.querySelector(".screen-off");
      img.style.display = "none";
      img.removeAttribute("src");
      off.textContent = "Fenêtre fermée — cliquez sur « Ouvrir »";
      off.classList.remove("hidden");
    }
  }
}

function refreshLiveFrames() {
  for (const s of document.querySelectorAll(".screen")) {
    if (!s.querySelector(".state").textContent.includes("onglet")) continue;
    const p = s.dataset.platform;
    const img = s.querySelector("img");
    const off = s.querySelector(".screen-off");
    img.onload = () => {
      img.style.display = "block";
      off.classList.add("hidden");
    };
    img.onerror = () => {
      img.style.display = "none";
      off.classList.remove("hidden");
      off.textContent = "Aperçu indisponible";
    };
    // jamais de cache : on repose l'image à chaque rafraîchissement
    img.src = "/api/screen?platform=" + p + "&t=" + Date.now();
  }
}

/* ── Liens en difficulté / erreur (section 4) ───────── */
function renderLinkErrors(errors) {
  const box = $("#link-errors");
  if (!box) return;
  const key = JSON.stringify(errors || []);
  if (key === box._key) return;          // rien n'a changé : on ne repeint pas
  box._key = key;
  box.innerHTML = "";
  if (!(errors || []).length) {
    box.appendChild(el("p", "hint",
      "Aucun lien en difficulté — tout s'est bien passé jusqu'ici."));
    return;
  }
  for (const e of errors.slice().reverse()) {
    const row = el("div", "link-err");
    // poubelle : supprime l'erreur ET met le lien en liste noire
    const bBin = el("button", "small danger link-bin", "🗑");
    bBin.title = "Supprimer cette erreur et bannir le lien (liste noire : " +
                 "jamais réimporté, même depuis un nouveau fichier Excel)";
    bBin.onclick = async () => {
      bBin.disabled = true;
      const res = await api("/api/link-errors/blacklist", { url: e.url });
      if (res) {
        renderLinkErrors(res.link_errors || []);
        renderBlacklist(res.blacklist || []);
        linkMsg2(res.message, res.ok);
      }
      refresh();
    };
    row.appendChild(bBin);
    const url = el("span", "url", e.url);
    url.title = e.url;
    row.appendChild(url);
    row.appendChild(el("span", "msg", e.message || "erreur inconnue"));
    row.appendChild(el("span", "ts",
      (e.ts || "").split("T").join(" ").slice(5, 16)));
    box.appendChild(row);
  }
}

function linkMsg2(text, ok) {
  // petit message sous la section 4 (réutilise le style .msg)
  let n = $("#link-errors-msg");
  if (!n) {
    n = el("div", "msg hidden");
    n.id = "link-errors-msg";
    $("#link-errors").after(n);
  }
  show(n, text, !!ok);
}

/* ── Liste noire (liens bannis) ─────────────────────── */
function renderBlacklist(items) {
  const box = $("#blacklist");
  if (!box) return;
  const key = JSON.stringify(items || []);
  const cnt = $("#blacklist-count");
  if (cnt) cnt.textContent = String((items || []).length);
  if (key === box._key) return;
  box._key = key;
  box.innerHTML = "";
  if (!(items || []).length) {
    box.appendChild(el("p", "hint", "Aucun lien banni."));
    return;
  }
  for (const b of items.slice().reverse()) {
    const row = el("div", "link-ban");
    const url = el("span", "url", b.url);
    url.title = b.url;
    row.appendChild(url);
    const bOut = el("button", "small", "Retirer");
    bOut.title = "Autoriser à nouveau ce lien (réimport possible)";
    bOut.onclick = async () => {
      bOut.disabled = true;
      const res = await api("/api/blacklist/remove", { url: b.url });
      if (res) renderBlacklist(res.blacklist || []);
      refresh();
    };
    row.appendChild(bOut);
    box.appendChild(row);
  }
}

/* ── Journal ─────────────────────────────────────────────── */
function renderJournal(entries) {
  const box = $("#journal");
  box.innerHTML = "";
  for (const e of entries.slice().reverse()) {
    const line = el("div", "line " + (e.level || "info"));
    line.appendChild(el("span", "ts", (e.ts || "").split("T").join(" ").slice(5)));
    line.appendChild(el("span", "src", "[" + (e.source || "socia") + "]"));
    line.appendChild(document.createTextNode(e.message || ""));
    box.appendChild(line);
  }
}
function flashJournal() {
  refresh(true);
}

/* ── Commande : aperçu du parseur ────────────────────────── */
let parseTimer = null;
async function previewCommand() {
  const q = $("#command").value.trim();
  const box = $("#parse-preview");
  if (!q) {
    box.classList.add("hidden");
    return;
  }
  const p = await api("/api/parse?q=" + encodeURIComponent(q));
  const bits = [];
  bits.push("plateforme : <b>" + (p.platform || "?") + "</b>");
  bits.push("type : <b>" + p.kind + "</b>");
  bits.push(
    "fréquence : <b>" +
      (p.interval_seconds ? fmtInterval(p.interval_seconds) : "?") +
      "</b>"
  );
  const checked = _links.filter((l) => l.selected).length;
  bits.push("cible : <b>" +
    (checked
      ? checked + " lien(s) coché(s)"
      : p.target === "groups" ? "groupes Facebook" : "profil") + "</b>");
  if (p.content) bits.push("contenu : <b>" + p.content.slice(0, 60) + "</b>");
  if (p.media) bits.push("photo : <b>" + p.media + "</b>");
  box.innerHTML = "J'ai compris → " + bits.join(" · ");
  box.classList.remove("hidden");
}

/* ── Média : insertion par fichier (bouton +), pas de chemin à taper ── */
async function uploadMedia(file) {
  if (!file) return;
  show($("#task-msg"), "Envoi du média…", true);
  try {
    const r = await fetch("/api/media", {
      method: "POST",
      headers: { "X-File-Name": file.name },
      body: file,
    });
    const j = await r.json();
    show($("#task-msg"), j.message || (j.ok ? "Média inséré" : "Envoi impossible"),
         !!j.ok);
    if (j.ok) {
      $("#f-media").value = j.name;
      _photos = [];          // nouveau média → nouvelle galerie de photos
      renderPhotos();
    }
  } catch (e) {
    show($("#task-msg"), "Serveur injoignable", false);
  }
}

function fmtInterval(sec) {
  const min = Math.round(sec / 60);
  if (min >= 60 && min % 60 === 0) {
    const h = min / 60;
    return (h <= 24 ? h + " h" : h / 24 + " j") + " (" + min + " min)";
  }
  return min + " min (" + sec + " s)";
}

function formatPeriod(t) {
  const fmt = (v) => String(v).replace("T", " ").slice(5, 16);   // 10-10 14:00
  if (t.start_at && t.end_at) return `du ${fmt(t.start_at)} au ${fmt(t.end_at)}`;
  if (t.start_at) return `à partir du ${fmt(t.start_at)}`;
  if (t.end_at) return `jusqu'au ${fmt(t.end_at)}`;
  return "";
}

/* ── Création de tâche ───────────────────────────────────── */
/* ── Photos Gemini : galerie validée avant lancement de la tâche ── */
let _photos = [];               // [{name, url}] générées et non retirées (X)

function renderPhotos() {
  const box = $("#photo-gallery");
  const cnt = $("#photo-count");
  if (!box || !cnt) return;
  box.innerHTML = "";
  if (!_photos.length) {
    box.classList.add("hidden");
    cnt.textContent = "aucune photo générée pour l'instant";
    return;
  }
  box.classList.remove("hidden");
  cnt.textContent =
    _photos.length + " photo(s) prête(s) — une sera utilisée par poste";
  _photos.forEach((p, i) => {
    const item = el("div", "pg-item");
    const img = el("img");
    img.src = p.url + "?v=" + p.name;
    img.alt = "photo Gemini " + (i + 1);
    const x = el("button", "pg-x", "X");
    x.type = "button";
    x.title = "Retirer cette photo de la liste";
    x.onclick = () => { _photos.splice(i, 1); renderPhotos(); };
    item.append(img, x);
    box.appendChild(item);
  });
}

async function genPhoto() {
  const media = $("#f-media").value.trim();
  if (!media) {
    show($("#task-msg"),
         "Insérez d'abord votre photo brute (bouton + du champ Média).",
         false);
    return;
  }
  const b = $("#f-photo-gen");
  b.disabled = true;
  b.textContent = "✨ Génération…";
  show($("#task-msg"), "Gemini crée votre photo (10 à 60 s)…", true);
  try {
    const res = await api("/api/gemini/generate", { media: media, count: 1 });
    if (res.ok && res.photos && res.photos.length) {
      _photos = _photos.concat(res.photos);
      renderPhotos();
      show($("#task-msg"), res.message, true);
    } else {
      show($("#task-msg"),
           res.message || "Génération impossible (voir le journal)", false);
    }
  } catch (e) {
    show($("#task-msg"), "Serveur injoignable", false);
  }
  b.disabled = false;
  b.textContent = "✨ Générer une photo";
}

/* ── Connexion Gemini : le compte Google de l'utilisateur, sans clé ── */
let _gemTimer = null;

function renderGemini(st) {
  const line = $("#gemini-status");
  const bC = $("#gemini-connect");
  const bD = $("#gemini-disconnect");
  if (!line) return;
  if (st.connected) {
    line.innerHTML = "✔ Connecté" +
      (st.email ? " avec <b>" + st.email + "</b>" : "") +
      " — vos photos sont générées par Gemini" +
      (st.model ? " (" + st.model + ")" : "");
    bC.classList.add("hidden");
    bD.classList.remove("hidden");
  } else if (st.phase === "opening") {
    line.textContent = "⏳ Fenêtre Google ouverte — choisissez votre e-mail, " +
      "la liaison se termine toute seule…";
    bC.disabled = true;
    bC.classList.remove("hidden");
    bD.classList.add("hidden");
  } else {
    line.innerHTML = "✖ Non connecté" +
      (st.message ? " — " + st.message : "") +
      (st.configured ? "" :
        " — suivez le guide « Première connexion ? » ci-dessous");
    bC.disabled = false;
    bC.classList.remove("hidden");
    bD.classList.add("hidden");
  }
  const cfs = $("#client-file-state");
  if (cfs) {
    cfs.textContent = st.configured
      ? "✔ Fichier Google déposé" +
        (st.project ? " (projet : " + st.project + ")" : "")
      : "Aucun fichier déposé.";
  }
}

async function refreshGemini() {
  try { renderGemini(await api("/api/gemini/status")); }
  catch (e) { /* prochain rafraîchissement */ }
}

function pollGemini() {
  clearInterval(_gemTimer);
  let n = 0;
  _gemTimer = setInterval(async () => {
    n += 1;
    try {
      const st = await api("/api/gemini/status");
      renderGemini(st);
      if (st.connected || st.phase === "error" || n >= 90) {
        clearInterval(_gemTimer);
      }
    } catch (e) { if (n >= 90) clearInterval(_gemTimer); }
  }, 2000);
}

async function connectGemini() {
  try {
    const res = await api("/api/gemini/connect", {});
    show($("#task-msg"), res.message, res.ok);
    renderGemini(await api("/api/gemini/status"));
    if (res.ok) pollGemini();
  } catch (e) { show($("#task-msg"), "Serveur injoignable", false); }
}

async function createTask() {
  const minutes = Number($("#f-interval").value) || 0;
  if (minutes && (minutes < 1 || minutes > 1440)) {
    show($("#task-msg"),
         "La fréquence va de 1 à 1440 minutes (24 h maximum).", false);
    return;
  }
  const payload = {
    command: $("#command").value.trim(),
    content: $("#f-content").value.trim(),
    platform: $("#f-platform").value,
    kind: $("#f-kind").value,
    media: $("#f-media").value.trim(),
    interval_seconds: minutes ? minutes * 60 : 0,
    start_at: $("#f-start").value,
    end_at: $("#f-end").value,
    max_targets: Number($("#f-quota").value) || 0,
    pretty_photo: $("#f-pretty").checked || _photos.length > 0,
    photos: _photos.map((p) => p.name),
  };
  ["platform", "kind"].forEach((k) => {
    if (!payload[k]) delete payload[k];
  });
  if (!payload.content) delete payload.content;
  if (!payload.interval_seconds) delete payload.interval_seconds;
  if (!payload.start_at) delete payload.start_at;
  if (!payload.end_at) delete payload.end_at;
  const res = await api("/api/tasks", payload);
  show($("#task-msg"), res.message, res.ok);
  if (res.ok) {
    $("#command").value = "";
    $("#f-content").value = "";
    $("#parse-preview").classList.add("hidden");
    _photos = [];           // la liste validée est embarquée dans la tâche
    renderPhotos();
  }
  refresh();
}

/* ── Rafraîchissement global ─────────────────────────────── */
async function refresh(full) {
  try {
    const s = await api("/api/state");

    const sb = $("#sched-badge");
    sb.textContent = s.scheduler && s.scheduler.running
      ? `programmateur : actif — ${s.scheduler.enabled} tâche(s) en cours`
      : "programmateur : arrêté";
    sb.className = "badge " + (s.scheduler && s.scheduler.running ? "on" : "off");

    const bb = $("#browser-badge");
    const br = s.browser || {};
    bb.textContent = br.playwright && br.chrome
      ? "navigateur : prêt"
      : !br.playwright
      ? "navigateur : playwright manquant"
      : "navigateur : Chrome manquant";
    bb.className = "badge " + (br.playwright && br.chrome ? "on" : "off");

    if (full !== false) renderAccounts(s.accounts || [], s.platforms || []);
    renderLinks(s.links || []);
    renderLive(s.windows || []);
    renderTasks(s.tasks || []);
    renderLinkErrors(s.link_errors || []);
    renderBlacklist(s.blacklist || []);
    renderJournal(s.journal || []);
    refreshLiveFrames();   // aperçu au plus frais, sans attendre le prochain tour
  } catch (e) {
    /* serveur momentanément indisponible : on réessaiera */
  }
}

document.addEventListener("DOMContentLoaded", () => {
  $("#create-task").onclick = createTask;
  // ── média : + ouvre le sélecteur de fichier, X retire le média ──
  $("#f-media-add").onclick = () => $("#f-file").click();
  $("#f-file").addEventListener("change", (e) => {
    const f = e.target.files && e.target.files[0];
    if (f) uploadMedia(f);
    e.target.value = "";           // on peut re-sélectionner le même fichier
  });
  $("#f-media-del").onclick = () => {
    $("#f-media").value = "";
    _photos = [];
    renderPhotos();
  };
  // ── fréquence : raccourcis 30 min / 1 h / 3 h / 12 h / 24 h ──
  document.querySelectorAll("#interval-chips .chip").forEach((b) => {
    b.onclick = () => { $("#f-interval").value = b.dataset.min; };
  });
  $("#command").addEventListener("input", () => {
    clearTimeout(parseTimer);
    parseTimer = setTimeout(previewCommand, 350);
  });
  $("#command").addEventListener("keydown", (e) => {
    if (e.key === "Enter") createTask();
  });
  // ── section 4 : vider la liste des liens en difficulté ──
  $("#clear-link-errors").onclick = async () => {
    await api("/api/link-errors/clear", {});
    refresh();
  };
  // ── liste noire : export Excel sur le PC (téléchargement direct) ──
  const bExp = $("#export-blacklist");
  if (bExp) bExp.onclick = () => { window.location.href = "/api/blacklist/export"; };
  // ── photos Gemini : génération + galerie validée (X = retirer) ──
  $("#f-photo-gen").onclick = genPhoto;
  renderPhotos();
  // ── connexion Gemini : compte Google, sans clé API ──
  $("#gemini-connect").onclick = connectGemini;
  $("#gemini-disconnect").onclick = async () => {
    const res = await api("/api/gemini/disconnect", {});
    show($("#task-msg"), res.message, res.ok);
    refreshGemini();
  };
  const cf = $("#f-client-file");
  if (cf) cf.addEventListener("change", async (e) => {
    const f = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!f) return;
    try {
      const r = await fetch("/api/gemini/client-secret", {
        method: "POST",
        headers: { "X-File-Name": f.name },
        body: f,
      });
      const j = await r.json();
      show($("#task-msg"), j.message, !!j.ok);
      refreshGemini();
    } catch (err) {
      show($("#task-msg"), "Serveur injoignable", false);
    }
  });
  refreshGemini();
  refresh();
  setInterval(refresh, 2000);
  // aperçu image des fenêtres : ~toutes les 0,7 s (uniquement si ouvertes)
  setInterval(refreshLiveFrames, 700);
  setTimeout(refreshLiveFrames, 500);
});
