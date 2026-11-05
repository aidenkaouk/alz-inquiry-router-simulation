// Team inbox. Teams on a case are equals: each sees the whole case and every team's
// status, and can change only its own. "Constituent Triage" only watches.
// SAFETY: all case text is added with textContent (never innerHTML).

var viewAs = null;
var teamNames = {};
var selected = null;
var lastSignature = "";
var inboxEl = document.getElementById("inbox");
var emptyEl = document.getElementById("inbox-empty");
var detailEl = document.getElementById("detail");
var pickerEl = document.getElementById("view-as");
var LABELS = { pending: "Pending", replied: "Replied", no_reply_needed: "No reply needed" };

function el(tag, cls, text) {
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}
function api(path, options) {
  return fetch(path, options).then(function (r) {
    if (!r.ok) { var err = new Error(path + " failed"); err.status = r.status; throw err; }
    return r.json();
  });
}
function post(path, body) {
  return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}
function statusChip(status) { return el("span", "status status-" + status, LABELS[status]); }
function teamChip(team) { var c = el("span", "chip" + (team === "HELP" ? " help" : ""), team); c.title = teamNames[team] || team; return c; }
function isTriage() { return viewAs === "TRIAGE"; }

// ---- Inbox list ----
function loadInbox() {
  api("/api/teams/" + viewAs + "/cases").then(function (all) {
    // A case leaves a team's inbox once that team has acted on it (replied or no
    // reply needed). Triage keeps a case until every team has acted. The server
    // still stores everything; this only decides what is listed.
    var rows = all.filter(function (r) { return isTriage() ? !r.closed : r.my_status === "pending"; });
    inboxEl.textContent = "";
    document.getElementById("inbox-title").textContent =
      (isTriage() ? "All open cases" : "Inbox") + " (" + rows.length + ")";
    emptyEl.hidden = rows.length > 0;
    emptyEl.textContent = all.length ? "Inbox is clear. Nothing waiting on this team." : "No approved cases for this team yet.";
    rows.forEach(function (r) {
      var li = el("li", (r.needs_human ? "crisis " : "") + (r.closed ? "done " : "") + (r.case_id === selected ? "selected" : ""));
      var top = el("div", "top");
      top.appendChild(el("span", "", r.case_id + (r.needs_human ? "  CRISIS" : "")));
      top.appendChild(r.closed ? el("span", "", "Closed") : isTriage() ? el("span", "", "Open") : statusChip(r.my_status));
      li.appendChild(top);
      li.appendChild(el("div", "", r.name));
      var teams = el("div", "teamrow");
      Object.keys(r.teams).forEach(function (t) { teams.appendChild(teamChip(t)); teams.appendChild(statusChip(r.teams[t])); });
      li.appendChild(teams);
      li.appendChild(el("div", "preview", r.preview));
      li.addEventListener("click", function () { selected = r.case_id; lastSignature = ""; loadInbox(); loadCase(); });
      inboxEl.appendChild(li);
    });
  }).catch(function (err) {
    emptyEl.hidden = false;
    emptyEl.textContent = err.status
      ? "The server answered with an error (" + err.status + "). Look at the Terminal window running the server."
      : "Cannot reach the demo server. Start it with: .venv/bin/python -m server.app";
  });
}

// ---- Case page ----
function loadCase(force) {
  if (!selected) return;
  api("/api/cases/" + selected).then(function (c) {
    // Only redraw when something changed, so a note being typed is not wiped.
    var sig = JSON.stringify([c.team_status, c.notes.length, viewAs]);
    if (!force && sig === lastSignature) return;
    lastSignature = sig;
    renderCase(c);
  });
}

// Show the message with this team's part highlighted. Built from text nodes only.
function highlighted(text, parts) {
  var box = el("div", "box message");
  var ranges = [];
  parts.forEach(function (p) {
    var i = text.indexOf(p);
    if (i >= 0) ranges.push([i, i + p.length]);
  });
  ranges.sort(function (a, b) { return a[0] - b[0]; });
  var pos = 0;
  ranges.forEach(function (r) {
    if (r[0] < pos) return;                       // skip overlaps
    if (r[0] > pos) box.appendChild(document.createTextNode(text.slice(pos, r[0])));
    box.appendChild(el("mark", "", text.slice(r[0], r[1])));
    pos = r[1];
  });
  box.appendChild(document.createTextNode(text.slice(pos)));
  return box;
}

function renderCase(c) {
  var r = c.route, mine = c.team_status[viewAs];
  var draft = detailEl.querySelector("textarea") ? detailEl.querySelector("textarea").value : "";
  detailEl.textContent = "";
  detailEl.appendChild(el("h2", "", c.case_id));
  var s = c.submitter;
  detailEl.appendChild(el("div", "muted", s.first_name + " " + s.last_name + "  |  " + s.email + "  |  ZIP " + s.zip + "  |  " + c.created));

  if (r.needs_human) detailEl.appendChild(el("div", "crisis-banner", "Crisis flag: a person must look at this case now."));
  if (c.closed) detailEl.appendChild(el("div", "decision", "This case is closed: every team has replied or needs no reply."));

  // Message, with this team's part highlighted.
  detailEl.appendChild(el("h3", "", "Message"));
  var myParts = r.segments.filter(function (g) { return g.team === viewAs; }).map(function (g) { return g.text; });
  detailEl.appendChild(highlighted(c.comments, myParts));
  if (!isTriage()) {
    detailEl.appendChild(el("p", "muted", myParts.length
      ? "Highlighted: the part of the message that belongs to your team. You can see the rest because teams share the whole case."
      : "No separate part was assigned to your team, so please read the whole message."));
  }
  if (r.handoff_note) { detailEl.appendChild(el("h3", "", "Handoff note")); detailEl.appendChild(el("div", "box", r.handoff_note)); }

  // Every team and its status.
  detailEl.appendChild(el("h3", "", "Teams on this case (all equals)"));
  var table = el("table");
  var head = el("tr");
  ["Team", "Status", "Their part of the message"].forEach(function (h) { head.appendChild(el("th", "", h)); });
  table.appendChild(head);
  Object.keys(c.team_status).forEach(function (t) {
    var row = el("tr", t === viewAs ? "me" : "");
    var parts = r.segments.filter(function (g) { return g.team === t; }).map(function (g) { return g.text; });
    var cell = el("td"); cell.appendChild(teamChip(t)); cell.appendChild(document.createTextNode(" " + (teamNames[t] || t)));
    row.appendChild(cell);
    var st = el("td"); st.appendChild(statusChip(c.team_status[t].status)); row.appendChild(st);
    row.appendChild(el("td", "", parts.join(" / ") || "(whole message)"));
    table.appendChild(row);
  });
  detailEl.appendChild(table);

  // My status: only my own, only if I am on the case. Triage watches.
  detailEl.appendChild(el("h3", "", "Your status"));
  if (isTriage()) {
    detailEl.appendChild(el("p", "muted", "Constituent Triage watches this case. Only each team can change its own status, but you can add notes below."));
  } else if (mine) {
    var row2 = el("div", "actions");
    ["replied", "no_reply_needed"].forEach(function (st) {
      var b = el("button", st === "replied" ? "approve" : "reroute", LABELS[st]);
      b.addEventListener("click", function () {
        post("/api/cases/" + c.case_id + "/teams/" + viewAs + "/status", { status: st, as_team: viewAs })
          .then(function () {
            // Acting on a case removes it from this team's inbox.
            selected = null; lastSignature = "";
            detailEl.textContent = "";
            detailEl.appendChild(el("h2", "", c.case_id));
            detailEl.appendChild(el("p", "", "Marked as " + LABELS[st] + ". This case has left your inbox."));
            detailEl.appendChild(el("p", "muted", "Other teams on the case can still see it until they act on it."));
            loadInbox();
          })
          .catch(function () { alert("Could not save that status."); });
      });
      row2.appendChild(b);
    });
    detailEl.appendChild(row2);
  } else {
    detailEl.appendChild(el("p", "muted", "Your team is not on this case."));
  }

  // Shared notes thread.
  detailEl.appendChild(el("h3", "", "Shared notes (every team can read these)"));
  if (!c.notes.length) detailEl.appendChild(el("p", "muted", "No notes yet."));
  c.notes.forEach(function (n) {
    var note = el("div", "note-item");
    note.appendChild(teamChip(n.team));
    note.appendChild(el("span", "muted", " " + n.time + "  "));
    note.appendChild(el("div", "", n.text));
    detailEl.appendChild(note);
  });
  if (mine || isTriage()) {
    var area = el("textarea", "note-input"); area.maxLength = 500; area.rows = 2; area.value = draft;
    area.placeholder = "Add a note for the other teams (max 500 characters)";
    var add = el("button", "reroute", "Add note");
    add.addEventListener("click", function () {
      if (!area.value.trim()) return;
      post("/api/cases/" + c.case_id + "/notes", { as_team: viewAs, text: area.value })
        .then(function () { lastSignature = ""; loadCase(true); });
    });
    detailEl.appendChild(area); detailEl.appendChild(add);
  }

  // Simulated handoff email(s).
  api("/api/cases/" + c.case_id + "/outbox").then(function (emails) {
    var shown = emails.filter(function (e) { return isTriage() || e.team_id === viewAs; });
    shown.forEach(function (e) {
      var d = el("details", "saw");
      d.appendChild(el("summary", "", "Simulated handoff email to " + e.to_name + " (" + e.to_role + ")  -  NOT SENT"));
      d.appendChild(el("p", "muted", "To: " + e.to_email + "   Subject: " + e.subject));
      d.appendChild(el("pre", "", e.body));
      detailEl.appendChild(d);
    });
  });
}

// ---- Start ----
api("/api/teams").then(function (list) {
  var all = list.concat([{ team_id: "TRIAGE", team_name: "Constituent Triage (watches all cases)" }]);
  all.forEach(function (t) {
    teamNames[t.team_id] = t.team_name;
    var o = document.createElement("option"); o.value = t.team_id; o.textContent = t.team_id + "  " + t.team_name;
    pickerEl.appendChild(o);
  });
  viewAs = new URLSearchParams(location.search).get("team") || "WALK";
  if (!teamNames[viewAs]) viewAs = "WALK";
  pickerEl.value = viewAs;
  pickerEl.addEventListener("change", function () {
    viewAs = pickerEl.value; selected = null; lastSignature = "";
    detailEl.textContent = ""; detailEl.appendChild(el("p", "muted", "Select a case from the inbox."));
    loadInbox();
  });
  loadInbox();
  setInterval(function () { loadInbox(); loadCase(); }, 4000);   // other teams' changes appear without reloading
});
