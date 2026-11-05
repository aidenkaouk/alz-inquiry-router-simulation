var MAX = 2500;
var form = document.getElementById("contact-form");
var comments = document.getElementById("comments");
var left = document.getElementById("chars-left");
var picker = document.getElementById("sample-picker");

// US states for the State dropdown.
"AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY"
  .split(" ").forEach(function (s) {
    var o = document.createElement("option"); o.value = s; o.textContent = s;
    document.getElementById("state").appendChild(o);
  });

function updateCount() { left.textContent = MAX - comments.value.length; }
comments.addEventListener("input", updateCount);
updateCount();

// Demo sample picker: fills the form so the demo does not need live typing.
window.SAMPLES.forEach(function (s, i) {
  var o = document.createElement("option"); o.value = i; o.textContent = s.id + ": " + s.label;
  picker.appendChild(o);
});
picker.addEventListener("change", function () {
  var s = window.SAMPLES[picker.value];
  if (!s) return;
  form.reset();
  Object.keys(s.submitter).forEach(function (k) {
    var el = document.getElementById(k.replace("_", "-"));
    if (el) el.value = s.submitter[k];
  });
  comments.value = s.comments;
  updateCount();
});

form.addEventListener("submit", function (e) {
  e.preventDefault();
  // Build the case record the intake server will receive. Real fields stay together here;
  // only the redacted Comments + case ID may ever go on to Claude (see CLAUDE.md privacy rules).
  var data = Object.fromEntries(new FormData(form).entries());
  data.language = window.LANG;
  var errorBox = document.getElementById("send-error");
  errorBox.hidden = true;
  sendInquiry(data).then(function (caseId) {
    document.getElementById("case-ref").textContent = caseId;
    form.hidden = true;
    document.getElementById("sample-box").hidden = true;
    document.getElementById("thanks").hidden = false;
  }).catch(function () {
    errorBox.textContent = window.STRINGS.sendError;
    errorBox.hidden = false;
  });
});

// Sends the form to the local demo server (server/app.py) and returns the case ID.
// The server keeps the contact details; only the redacted Comments go on to Claude.
function sendInquiry(data) {
  return fetch("/api/inquiries", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  }).then(function (r) {
    if (!r.ok) throw new Error("send failed");
    return r.json();
  }).then(function (body) { return body.case_id; });
}

document.getElementById("again").addEventListener("click", function () {
  form.reset(); updateCount();
  form.hidden = false;
  document.getElementById("sample-box").hidden = false;
  document.getElementById("thanks").hidden = true;
});
document.getElementById("cancel").addEventListener("click", function (e) {
  e.preventDefault(); form.reset(); updateCount();
});
