// Waiting: a stand-in for the screens later slices add (personality pick,
// acting and guessing, scores and awards). It shows the room and the game's status.

import { h } from "../dom.js";

const STATUS_TEXT = {
  personality_selection: "Teams are picking personalities",
  playing: "The game is on",
  finished: "Game over",
};

export function mount(root) {
  const code = h("p", { class: "room-code" });
  const status = h("h2", {});
  const team = h("p", { class: "my-team" });
  root.append(
    h(
      "section",
      { class: "screen center" },
      h("p", { class: "eyebrow" }, "Room code"),
      code,
      status,
      team,
      h("p", { class: "note" }, "This screen is coming soon. Keep this page open."),
    ),
  );

  function update(state) {
    const view = state.view;
    const myTeam = view.teams.find((t) => t.id === view.team_id);
    code.textContent = view.room_code;
    status.textContent = STATUS_TEXT[view.status] ?? view.status;
    team.replaceChildren(
      ...(myTeam ? [h("span", { class: "team-dot", style: { "--team": myTeam.color } }), `You're on ${myTeam.name}`] : []),
    );
  }

  return { update, unmount() {} };
}
