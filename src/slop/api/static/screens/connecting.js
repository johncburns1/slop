// Connecting: shown while a saved session is being rejoined after a reload.

import { h } from "../dom.js";

export function mount(root) {
  root.append(h("section", { class: "screen center" }, h("p", { class: "note cursor" }, "reconnecting to your game")));
  return { update() {}, unmount() {} };
}
