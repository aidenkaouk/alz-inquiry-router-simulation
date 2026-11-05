// Staff console. SAFETY: all case text is added with textContent (never innerHTML),
// so a hostile message like "<script>..." is shown as plain text and cannot run.

var queueEl = document.getElementById("queue");
var emptyEl = document.getElementById("queue-empty");
var detailEl = document.getElementById("detail");
var selected = null;
var teamNames = {};

function el(tag, cls, text) {
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}
function api(path, options) {
  return fetch(path, options).then(function (r) {
    if (!r.ok) throw new Error(path + " failed");
    return r.json();
  });
}
function chip(team) {
  // The router's "TRIAGE" just means it could not decide; staff are the triage team.
  var unsorted = team === "TRIAGE";
  var c = el("span", "chip" + (unsorted ? " triage" : team === "HELP" ? " help" : ""), unsorted ? "UNSORTED" : team);
  c.title = unsorted ? "The router could not decide" : (teamNames[team] || team);
  return c;
}

// ---- "Done for now" panda: shown when every case in the queue has been resolved ----
var pandaShown = false;
var PANDA_SVG =
  '<svg viewBox="0 0 320 200" width="320" height="200" role="img" aria-label="A panda sleeping">' +
  '<ellipse cx="170" cy="182" rx="130" ry="8" fill="#000" opacity="0.08"/>' +
  '<ellipse cx="190" cy="140" rx="96" ry="46" fill="#fff" stroke="#333" stroke-width="3"/>' +
  '<ellipse cx="250" cy="170" rx="22" ry="16" fill="#333"/><ellipse cx="130" cy="172" rx="22" ry="14" fill="#333"/>' +
  '<path d="M150 112 Q190 92 240 106" fill="none" stroke="#333" stroke-width="22" stroke-linecap="round"/>' +
  '<circle cx="96" cy="112" r="46" fill="#fff" stroke="#333" stroke-width="3"/>' +
  '<circle cx="66" cy="76" r="15" fill="#333"/><circle cx="124" cy="78" r="15" fill="#333"/>' +
  '<ellipse cx="80" cy="108" rx="13" ry="10" fill="#333" transform="rotate(-20 80 108)"/>' +
  '<ellipse cx="114" cy="108" rx="13" ry="10" fill="#333" transform="rotate(20 114 108)"/>' +
  '<path d="M72 109 Q80 115 88 109" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"/>' +
  '<path d="M106 109 Q114 115 122 109" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"/>' +
  '<ellipse cx="97" cy="124" rx="7" ry="5" fill="#333"/>' +
  '<path d="M90 133 Q97 138 104 133" fill="none" stroke="#333" stroke-width="2.5" stroke-linecap="round"/>' +
  '<g class="zzz" fill="#47135f" font-family="Helvetica, Arial, sans-serif" font-weight="700">' +
  '<text x="150" y="70" font-size="26">Z</text><text x="176" y="46" font-size="20">z</text><text x="196" y="26" font-size="15">z</text></g>' +
  '</svg>';   // fixed drawing, no case data, so setting innerHTML here is safe

function showPrompt() {
  pandaShown = false;
  detailEl.textContent = "";
  detailEl.appendChild(el("p", "muted", "Select a case from the queue."));
}
function showPanda() {
  pandaShown = true;
  selected = null;
  detailEl.textContent = "";
  var box = el("div", "panda");
  var art = el("div", "panda-art");
  art.innerHTML = PANDA_SVG;
  box.appendChild(art);
  box.appendChild(el("h2", "", "Done for now"));
  box.appendChild(el("p", "muted", "The queue is clear. New cases will appear here."));
  detailEl.appendChild(box);
}

// ---- Queue ----
// "Queue" = cases waiting for a decision. Approved cases leave the list (they stay
// saved on the server).
function renderRow(r) {
  var li = el("li", (r.needs_human ? "crisis " : "") + (r.case_id === selected ? "selected" : ""));
  var top = el("div", "top");
  top.appendChild(el("span", "", r.case_id + (r.needs_human ? "  CRISIS" : "")));
  top.appendChild(el("span", "", "Needs review"));
  li.appendChild(top);
  li.appendChild(el("div", "", r.name));
  var teams = el("div");
  r.teams.forEach(function (t) { teams.appendChild(chip(t)); });
  li.appendChild(teams);
  li.appendChild(el("div", "preview", r.preview));
  li.addEventListener("click", function () { selected = r.case_id; loadQueue(); loadCase(r.case_id); });
  return li;
}

function loadQueue() {
  api("/api/cases").then(function (rows) {
    var open = rows.filter(function (r) { return r.status === "needs_review"; });
    queueEl.textContent = "";
    open.forEach(function (r) { queueEl.appendChild(renderRow(r)); });
    emptyEl.hidden = open.length > 0;
    emptyEl.textContent = rows.length ? "Queue is clear. Nice work." : "No cases yet. Submit one from the Contact Us form.";
    if (open.length === 0 && rows.length > 0) {
      if (!pandaShown) showPanda();          // everything resolved: panda replaces the last case
    } else if (pandaShown) {
      showPrompt();                          // a new case arrived: wake up
    }
  }).catch(function () {
    emptyEl.hidden = false;
    emptyEl.textContent = "Cannot reach the demo server. Start it with: .venv/bin/python -m server.app";
  });
}

// ---- Case detail ----
function loadCase(id) {
  api("/api/cases/" + id).then(renderCase);
}

function renderCase(c) {
  pandaShown = false;
  var r = c.route;
  detailEl.textContent = "";
  detailEl.appendChild(el("h2", "", c.case_id));
  var s = c.submitter;
  detailEl.appendChild(el("div", "muted",
    s.first_name + " " + s.last_name + "  |  " + s.email + "  |  ZIP " + s.zip + "  |  " + c.created));

  if (r.needs_human) {
    var b = el("div", "crisis-banner", "A person must look at this now. The Helpline (HELP) is on this case.");
    var why = [];
    if (r.crisis_keywords.length) why.push("Keyword check: " + r.crisis_keywords.join(", "));
    if (r.claude_crisis) why.push("Claude also flagged crisis");
    b.appendChild(el("small", "", why.join("  |  ")));
    detailEl.appendChild(b);
  }

  detailEl.appendChild(el("h3", "", "Message"));
  detailEl.appendChild(el("div", "box message", c.comments));

  detailEl.appendChild(el("h3", "", "Router suggestion (you decide)"));
  var teams = el("div");
  r.teams.forEach(function (t) { teams.appendChild(chip(t)); });
  detailEl.appendChild(teams);
  if (r.teams.indexOf("TRIAGE") !== -1) {
    detailEl.appendChild(el("div", "reasons", "The router could not decide. Please sort this one yourself."));
  }
  if (r.triage_reasons.length) detailEl.appendChild(el("div", "reasons", "Why the router was unsure: " + r.triage_reasons.join("; ")));
  r.staff_flags.forEach(function (f) { detailEl.appendChild(el("div", "flag", "Staff flag: " + f)); });

  if (r.segments.length) {
    detailEl.appendChild(el("h3", "", "How Claude split the message"));
    var t = el("table");
    var head = el("tr");
    ["Part of the message", "Team", "Confidence", "Reason"].forEach(function (h) { head.appendChild(el("th", "", h)); });
    t.appendChild(head);
    r.segments.forEach(function (seg) {
      var row = el("tr");
      [seg.text, seg.team === "TRIAGE" ? "UNSORTED" : seg.team, Math.round(seg.confidence * 100) + "%", seg.reason].forEach(function (v) { row.appendChild(el("td", "", v)); });
      t.appendChild(row);
    });
    detailEl.appendChild(t);
  }
  if (r.handoff_note) {
    detailEl.appendChild(el("h3", "", "Handoff note"));
    detailEl.appendChild(el("div", "box", r.handoff_note));
  }

  renderActions(c);

  // What Claude saw: the exact request text, so reviewers can check the privacy rules.
  var d = el("details", "saw");
  d.appendChild(el("summary", "", "What Claude saw"));
  d.appendChild(el("p", "muted", "Only the case ID and the redacted Comments. No name, email, phone or address."));
  d.appendChild(el("pre", "", r.what_claude_saw || "(Nothing was sent to Claude)"));
  var counts = Object.keys(r.redacted_counts || {}).map(function (k) { return k + ": " + r.redacted_counts[k]; });
  d.appendChild(el("p", "", "Removed before sending: " + (counts.join(", ") || "nothing")));
  d.appendChild(el("p", "muted", "Answer source: " + r.source + (r.error ? "  |  " + r.error : "")));
  detailEl.appendChild(d);
}

function renderActions(c) {
  detailEl.appendChild(el("h3", "", "Decision"));
  if (c.status === "approved") {
    var done = el("div", "decision");
    done.appendChild(el("strong", "", "Approved: "));
    c.decision.teams.forEach(function (t) { done.appendChild(chip(t)); });
    if (c.decision.changed) {
      var was = c.decision.suggested_teams.length ? c.decision.suggested_teams.join(", ") : "no suggestion";
      done.appendChild(el("div", "", "Staff changed the router's suggestion (" + was + ")."));
    }
    done.appendChild(el("div", "muted", "Recorded only. Nothing was sent anywhere."));
    detailEl.appendChild(done);
    return;
  }
  // Tick or untick teams, then press Approve. You are the triage team, so TRIAGE is not listed.
  detailEl.appendChild(el("p", "muted", "Teams for this case. Change them if the suggestion is wrong, then approve."));
  var suggested = c.route.teams.filter(function (t) { return t !== "TRIAGE"; });
  var box = el("div", "reroute-box");
  Object.keys(teamNames).forEach(function (id) {
    var label = el("label");
    var cb = el("input"); cb.type = "checkbox"; cb.value = id;
    cb.checked = suggested.indexOf(id) !== -1;
    if (id === "HELP" && c.route.needs_human) { cb.checked = true; cb.disabled = true; }  // crisis: HELP is required
    label.appendChild(cb); label.appendChild(document.createTextNode(" " + id + " " + teamNames[id]));
    box.appendChild(label);
  });
  detailEl.appendChild(box);

  var row = el("div", "actions");
  var approve = el("button", "approve", "Approve");
  row.appendChild(approve);
  detailEl.appendChild(row);

  // An unsorted case stays in the queue until at least one team is chosen:
  // Approve is greyed out until then.
  function pickedTeams() {
    return Array.prototype.map.call(box.querySelectorAll("input:checked"), function (i) { return i.value; });
  }
  function updateApprove() {
    approve.disabled = pickedTeams().length === 0;
    approve.title = approve.disabled ? "Tick at least one team to approve" : "";
  }
  box.addEventListener("change", updateApprove);
  updateApprove();

  approve.addEventListener("click", function () {
    decide(c.case_id, { action: "approve", teams: pickedTeams() });
  });
}

function decide(id, body) {
  api("/api/cases/" + id + "/decision", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
  }).then(function (c) { renderCase(c); loadQueue(); })
    .catch(function () { alert("Could not save. Pick at least one team."); });
}

// ---- Start ----
api("/api/teams").then(function (list) {
  list.forEach(function (t) { teamNames[t.team_id] = t.team_name; });
  loadQueue();
  setInterval(loadQueue, 4000);   // new submissions appear without reloading
});
