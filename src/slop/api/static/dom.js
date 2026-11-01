// Small DOM helpers shared by the screens.

/**
 * Make an element: h("button", { class: "primary", onclick }, "Go").
 * Attributes starting with "on" become event listeners; children may be
 * strings, nodes, or (nested) arrays of them, and null/false are skipped.
 */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (key === "style" && typeof value === "object") {
      for (const [prop, v] of Object.entries(value)) el.style.setProperty(prop, v);
    }
    else el.setAttribute(key, value === true ? "" : value);
  }
  el.append(...children.flat(Infinity).filter((c) => c !== null && c !== false && c !== undefined));
  return el;
}

/**
 * Run `action` while `button` shows it is busy, and show any error in
 * `errorBox` (cleared first). Returns true if the action succeeded.
 */
export async function attempt(button, errorBox, action) {
  errorBox.textContent = "";
  errorBox.hidden = true;
  button.disabled = true;
  try {
    await action();
    return true;
  } catch (error) {
    errorBox.textContent = error?.code ? error.message : "couldn't reach the server. try again.";
    errorBox.hidden = false;
    return false;
  } finally {
    button.disabled = false;
  }
}

/** An empty inline error box, hidden until `attempt` fills it. */
export function errorBox() {
  return h("p", { class: "error", role: "alert", hidden: true });
}

/** Draw `text` in a double-line box, as text: ╔═══╗ / ║ X ║ / ╚═══╝. */
export function asciiBox(text) {
  const inner = ` ${text} `;
  const bar = "═".repeat(inner.length);
  return `╔${bar}╗\n║${inner}║\n╚${bar}╝`;
}

/** A room code drawn big in a box, spaced out so it reads across a room. */
export function roomCodeBox() {
  return h("pre", { class: "room-code", "aria-label": "Room code" });
}

export function setRoomCode(box, code) {
  box.textContent = asciiBox(code.split("").join(" "));
  box.setAttribute("aria-label", `Room code ${code}`);
}
