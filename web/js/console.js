// Staff console. SAFETY: all case text is added with textContent (never innerHTML),
// so a hostile message like "<script>..." is shown as plain text and cannot run.

var queueEl = document.getElementById("queue");
var emptyEl = document.getElementById("queue-empty");
var followupEl = document.getElementById("followup");
var followupHeadEl = document.getElementById("followup-head");
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

// ---- Queue ----
// "Queue" = cases waiting for a decision. Approved cases leave the list (they stay
// saved on the server). Follow-up cases wait in their own list so none are lost.
function renderRow(r) {
  var li = el("li", (r.needs_human ? "crisis " : "") + (r.status === "needs_followup" ? "followup " : "") +
                    (r.case_id === selected ? "selected" : ""));
  var top = el("div", "top");
  top.appendChild(el("span", "", r.case_id + (r.needs_human ? "  CRISIS" : "")));
  top.appendChild(el("span", "", r.status === "needs_followup" ? "Follow-up" : "Needs review"));
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
    var followups = rows.filter(function (r) { return r.status === "needs_followup"; });
    queueEl.textContent = "";
    followupEl.textContent = "";
    open.forEach(function (r) { queueEl.appendChild(renderRow(r)); });
    followups.forEach(function (r) { followupEl.appendChild(renderRow(r)); });
    emptyEl.hidden = open.length > 0;
    emptyEl.textContent = rows.length ? "Queue is clear. Nice work." : "No cases yet. Submit one from the Contact Us form.";
    followupHeadEl.hidden = followups.length === 0;
    followupHeadEl.textContent = "Follow-up (" + followups.length + ")";
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
      [seg.text, seg.team, Math.round(seg.confidence * 100) + "%", seg.reason].forEach(function (v) { row.appendChild(el("td", "", v)); });
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
  if (c.status === "needs_followup") {
    var fu = el("div", "flag", "Follow-up needed: " + (c.decision.note || "(no note)") + "  You can still sort and approve it below.");
    detailEl.appendChild(fu);
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

  var note = el("input", "note"); note.type = "text"; note.maxLength = 300;
  note.placeholder = "Optional note: what do you need to find out?";
  var followup = el("button", "triage-btn", "Can't sort this: needs follow-up");
  var fuRow = el("div", "actions");
  fuRow.appendChild(note); fuRow.appendChild(followup);
  detailEl.appendChild(fuRow);

  approve.addEventListener("click", function () {
    var picked = Array.prototype.map.call(box.querySelectorAll("input:checked"), function (i) { return i.value; });
    decide(c.case_id, { action: "approve", teams: picked });
  });
  followup.addEventListener("click", function () { decide(c.case_id, { action: "followup", note: note.value }); });
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
