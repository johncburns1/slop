// The host's way to remove a player: a "remove" button next to each other player,
// in the lobby's team lists and in the host menu (host-menu.js) once the game has
// started. Either asks first, then sends `kick_player`.

import { attempt, h } from "../dom.js";

/** A host-only button that asks, then removes `player`. Errors go to `errors`. */
export function removeButton(game, player, errors) {
  const button = h("button", { type: "button", class: "small remove", "aria-label": `Remove ${player.name}` }, "remove");
  button.addEventListener("click", () => {
    if (confirm(`Remove ${player.name} from the game? They can't come back as this player.`)) {
      attempt(button, errors, () => game.kickPlayer(player.id));
    }
  });
  return button;
}

/** Every player as a file tree with their team's color, and a remove button for all but the viewer. */
export function removablePlayers(game, view, errors) {
  const teams = new Map(view.teams.map((t) => [t.id, t]));
  return view.players.map((p, i) => {
    const isMe = p.id === view.player_id;
    const team = teams.get(p.team_id);
    return h(
      "li",
      { class: isMe ? "player removable me" : "player removable" },
      h("span", { class: "branch", "aria-hidden": "true" }, i === view.players.length - 1 ? "└─ " : "├─ "),
      h(
        "span",
        { class: "player-name" },
        team ? h("span", { class: "team-dot", style: { "--team": team.color }, "aria-hidden": "true" }, "■ ") : null,
        p.name,
        isMe ? h("span", { class: "tag" }, " <you>") : null,
      ),
      isMe ? null : removeButton(game, p, errors),
    );
  });
}
