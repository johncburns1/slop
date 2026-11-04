// Entry point: shows the screen for where this player is in the game.
//
// Each screen module exports `mount(root, game)`, which builds the screen
// once and returns `{ update(state), unmount() }`. The screen is swapped only
// when `screenFor` picks a different one, so typing in a form survives other
// players' updates. Later slices add a screen module and a line to `screenFor`.

import { game } from "./game.js";
import * as connecting from "./screens/connecting.js";
import * as finished from "./screens/finished.js";
import * as home from "./screens/home.js";
import * as lobby from "./screens/lobby.js";
import * as waiting from "./screens/waiting.js";

function screenFor(state) {
  if (state.restoring) return connecting;
  if (!state.view) return home;
  switch (state.view.status) {
    case "lobby":
      return lobby;
    case "finished":
      return finished;
    default:
      return waiting;
  }
}

const root = document.getElementById("app");
const banner = document.getElementById("offline");
let current = null;
let screen = null;

function render(state) {
  banner.hidden = state.connected !== false;
  const next = screenFor(state);
  if (next !== current) {
    screen?.unmount();
    root.replaceChildren();
    current = next;
    screen = next.mount(root, game);
  }
  screen.update(state);
}

game.subscribe(render);
render(game.state);
