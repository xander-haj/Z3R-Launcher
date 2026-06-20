export function createSpriteBrowserHost() {
  const host = document.createElement("div");
  let closeCallback = null;

  host.className = "link-sprite-browser-host";
  host.hidden = true;

  const browser = {
    editor: null,
    host,
    attachEditor(editor) {
      browser.editor = editor;
    },
    isOpen() {
      return !host.hidden;
    },
    show(node, onClose) {
      closeCallback = onClose;
      host.replaceChildren(node);
      host.hidden = false;

      if (browser.editor) {
        browser.editor.hidden = true;
      }
    },
    hide() {
      const callback = closeCallback;
      closeCallback = null;
      host.textContent = "";
      host.hidden = true;

      if (browser.editor) {
        browser.editor.hidden = false;
      }

      callback?.();
    },
  };

  return browser;
}
