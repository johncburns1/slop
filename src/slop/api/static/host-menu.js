// The host's menu during the game: a small [ sudo ] toggle above every screen
// after the lobby, with the controls the host has at any point.
//
// Restart sends everyone back to the lobby with the same teams (see
// `restart_game` in src/slop/api/messages.py), and each player can be removed
// (`kick_player`). Skipping a stalled turn lives on the playing screen, since
// it only applies while a team writes its prompt.

import { attempt, errorBox, h } from "./dom.js";
import { removablePlayers } from "./screens/players.js";

export function mount(root, game) {
  const restartButton = h("button", { type: "button", class: "secondary" }, "Restart game");
  const restartError = errorBox();
  const playerList = h("ul", { class: "players" });
  const removeError = errorBox();
  const panel = h(
    "div",
    { class: "card host" },
    h("h2", {}, "sudo"),
    h("p", { class: "note" }, "back to the lobby, same players and teams. scores, rounds, and personalities reset."),
    restartButton,
    restartError,
    h("h3", {}, "players"),
    h("p", { class: "note" }, "remove anyone who shouldn't be here."),
    playerList,
    removeError,
  );
  const menu = h("details", { class: "host-menu" }, h("summary", {}, "sudo"), panel);
  restartButton.addEventListener("click", async () => {
    if (!confirm("Restart the game? Everyone goes back to the lobby and scores reset.")) return;
    if (await attempt(restartButton, restartError, () => game.restartGame())) menu.open = false;
  });
  root.append(menu);

  function update(state) {
    const status = state.view?.status;
    const shown = !state.restoring && Boolean(game.me()?.is_host) && Boolean(status) && status !== "lobby";
    root.hidden = !shown;
    if (!shown) {
      menu.open = false;
      restartError.hidden = true;
      removeError.hidden = true;
    }
    if (shown) playerList.replaceChildren(...removablePlayers(game, state.view, removeError));
  }

  return { update };
}
