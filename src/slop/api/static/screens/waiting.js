// Waiting: a stand-in for the screens later slices add (personality pick,
// acting and guessing, scores and awards). It shows the room and the game's status.

import { h, roomCodeBox, setRoomCode } from "../dom.js";

const STATUS_TEXT = {
  personality_selection: "teams are picking personalities",
  playing: "the game is on",
  finished: "game over",
};

export function mount(root) {
  const code = roomCodeBox();
  const status = h("h2", { class: "cursor" });
  const team = h("p", { class: "my-team" });
  root.append(
    h(
      "section",
      { class: "screen center" },
      h("p", { class: "eyebrow" }, "room code"),
      code,
      status,
      team,
      h("p", { class: "note" }, "this screen is coming soon. keep this page open."),
    ),
  );

  function update(state) {
    const view = state.view;
    const myTeam = view.teams.find((t) => t.id === view.team_id);
    setRoomCode(code, view.room_code);
    status.textContent = `> ${STATUS_TEXT[view.status] ?? view.status}`;
    team.replaceChildren(
      ...(myTeam
        ? [h("span", { class: "team-dot", style: { "--team": myTeam.color } }, "■"), ` you're on ${myTeam.name}`]
        : []),
    );
  }

  return { update, unmount() {} };
}
