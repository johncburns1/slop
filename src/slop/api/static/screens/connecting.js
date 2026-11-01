// Connecting: shown while a saved session is being rejoined after a reload.

import { h } from "../dom.js";

export function mount(root) {
  root.append(h("section", { class: "screen center" }, h("p", { class: "note" }, "Getting you back in…")));
  return { update() {}, unmount() {} };
}
