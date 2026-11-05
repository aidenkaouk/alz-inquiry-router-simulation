// Fills every element marked data-i18n="key" (or data-i18n-placeholder="key") from window.STRINGS.
document.querySelectorAll("[data-i18n]").forEach(function (el) {
  var text = window.STRINGS[el.dataset.i18n];
  if (text !== undefined) el.textContent = text;
});
document.querySelectorAll("[data-i18n-placeholder]").forEach(function (el) {
  var text = window.STRINGS[el.dataset.i18nPlaceholder];
  if (text !== undefined) el.placeholder = text;
});
document.documentElement.lang = window.LANG;
