// Opens the tracker in a full browser tab when the toolbar button is clicked.
// No content scripts, no tab inspection and no network interception: the
// extension never reads Lumen pages or Lumen tokens.
chrome.action.onClicked.addListener(() => {
  chrome.tabs.create({ url: chrome.runtime.getURL("index.html") });
});
