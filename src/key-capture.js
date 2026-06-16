// Translates a single browser keydown event into a zelda3.ini-compatible key name.
// Used by controller-overlay.js's KeyMap edit mode (capture-on-keypress): the user
// clicks a button label, the next keydown is routed through captureKeyName, and the
// returned string is what gets written into the Controls = ... line.
//
// Returns null when the press is a bare modifier (Shift/Ctrl/Alt with no main key) so
// the caller can keep listening for the actual binding.

// Maps JS event.code (preferred where it differentiates left/right modifiers and arrow
// keys reliably) onto the SDL2 key name strings zelda3.ini expects. Falls through to a
// secondary event.key lookup for normal printable characters.
const CODE_TO_INI = {
  ArrowUp: "Up",
  ArrowDown: "Down",
  ArrowLeft: "Left",
  ArrowRight: "Right",
  Enter: "Return",
  NumpadEnter: "Return",
  ShiftRight: "Right Shift",
  ShiftLeft: "Left Shift",
  Tab: "Tab",
  Space: "Space",
  Escape: "Escape",
  Backspace: "Backspace",
  Delete: "Delete",
  Home: "Home",
  End: "End",
  PageUp: "PageUp",
  PageDown: "PageDown",
  Insert: "Insert",
  Minus: "-",
  Equal: "=",
  BracketLeft: "[",
  BracketRight: "]",
  Backslash: "\\",
  Semicolon: ";",
  Quote: "'",
  Comma: ",",
  Period: ".",
  Slash: "/",
  Backquote: "`",
};

// Bare modifier keys returned from event.code; pressing only one of these in listening
// mode is not enough to bind a button. The capture loop must wait for a real key.
const BARE_MODIFIERS = new Set([
  "ShiftLeft",
  "ShiftRight",
  "ControlLeft",
  "ControlRight",
  "AltLeft",
  "AltRight",
  "MetaLeft",
  "MetaRight",
]);

// Returns the ini-formatted key name for one keydown event, or null when the press is
// itself a bare modifier (so the caller continues listening).
export function captureKeyName(event) {
  // Don't bind modifier-only presses; wait for the user to release-and-press a real key.
  if (BARE_MODIFIERS.has(event.code)) {
    return null;
  }

  const main = mainKeyName(event);
  if (!main) {
    return null;
  }

  // Compose with leading Ctrl+ / Shift+ / Alt+ modifiers. The zelda3 ini documents this
  // exact order, so always emit Ctrl before Shift before Alt for repeatability.
  const parts = [];
  if (event.ctrlKey) parts.push("Ctrl");
  if (event.shiftKey && main !== "Right Shift" && main !== "Left Shift") parts.push("Shift");
  if (event.altKey) parts.push("Alt");
  parts.push(main);
  return parts.join("+");
}

// Picks the best ini name for the non-modifier key portion of the event.
function mainKeyName(event) {
  // Function keys: event.key is already "F1".."F24" which matches the ini spelling.
  if (/^F\d+$/.test(event.key)) {
    return event.key;
  }

  // Use the CODE_TO_INI table first because event.code distinguishes ShiftLeft vs
  // ShiftRight and is layout-independent for arrow / control keys.
  if (CODE_TO_INI[event.code]) {
    return CODE_TO_INI[event.code];
  }

  // event.key handles the printable letters and digits, but it returns shifted forms
  // ("A" with Shift held) — the ini stores the bare letter and uses Shift+ as a prefix,
  // so we always lowercase single-character keys here.
  if (event.key && event.key.length === 1) {
    return event.key.toLowerCase();
  }

  // Anything left over (PrintScreen, ContextMenu, etc.) is rare enough that the user
  // can hand-edit the ini if they ever need it. Return null so capture stays armed.
  return null;
}
