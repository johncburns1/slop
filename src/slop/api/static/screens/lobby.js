// Lobby: the room code, who's here, and forming teams until the host starts.

import { attempt, errorBox, h } from "../dom.js";

const TEAM_COLORS = ["#E53935", "#1E88E5", "#43A047", "#FDD835", "#8E24AA", "#FB8C00", "#00ACC1", "#D81B60"];

export function mount(root, game) {
  const code = h("p", { class: "room-code", "aria-label": "Room code" });
  const leaveButton = h("button", { type: "button", class: "link" }, "Leave");
  const leaveError = errorBox();
  leaveButton.addEventListener("click", () => {
    if (confirm("Leave this game?")) attempt(leaveButton, leaveError, () => game.leave());
  });

  const teamList = h("ul", { class: "teams" });
  const teamError = errorBox();
  const unassigned = h("div", { class: "unassigned" });

  const teamName = h("input", { id: "team-name", maxlength: 20, placeholder: "Team name", autocomplete: "off" });
  const swatches = h("div", { class: "swatches", role: "radiogroup", "aria-label": "Team color" });
  for (const [i, color] of TEAM_COLORS.entries()) {
    swatches.append(
      h(
        "label",
        { class: "swatch", style: { "--swatch": color }, title: color },
        h("input", { type: "radio", name: "team-color", value: color, checked: i === 0, "aria-label": color }),
      ),
    );
  }
  const createButton = h("button", { type: "submit", class: "secondary" }, "Create team");
  const createError = errorBox();
  const createForm = h(
    "form",
    {
      class: "card",
      onsubmit: async (event) => {
        event.preventDefault();
        const color = swatches.querySelector("input:checked")?.value ?? "";
        const ok = await attempt(createButton, createError, () => game.createTeam(teamName.value, color));
        if (ok) teamName.value = "";
      },
    },
    h("h2", {}, "New team"),
    h("label", { for: "team-name", class: "visually-hidden" }, "Team name"),
    teamName,
    swatches,
    createButton,
    createError,
  );

  const shuffleButton = h("button", { type: "button", class: "secondary" }, "Shuffle teams");
  const startButton = h("button", { type: "button", class: "primary" }, "Start personality selection");
  const hostError = errorBox();
  shuffleButton.addEventListener("click", () => attempt(shuffleButton, hostError, () => game.shuffleTeams()));
  startButton.addEventListener("click", () => attempt(startButton, hostError, () => game.startPersonalitySelection()));
  const hostControls = h("div", { class: "card host" }, h("h2", {}, "You're the host"), shuffleButton, startButton, hostError);
  const waitingNote = h("p", { class: "note" });

  root.append(
    h(
      "section",
      { class: "screen lobby" },
      h("header", { class: "lobby-header" }, h("div", {}, h("p", { class: "eyebrow" }, "Room code"), code), leaveButton),
      leaveError,
      h("h2", { class: "section-title" }, "Teams"),
      teamList,
      teamError,
      unassigned,
      createForm,
      hostControls,
      waitingNote,
    ),
  );

  function joinButton(team) {
    const button = h("button", { type: "button", class: "small" }, "Join");
    button.addEventListener("click", () => attempt(button, teamError, () => game.joinTeam(team.id)));
    return button;
  }

  let lastTeams = null;

  function update(state) {
    const view = state.view;
    // A host error like "You need at least 2 teams" is stale once the teams change.
    const teams = JSON.stringify(view.players.map((p) => [p.id, p.team_id]));
    if (lastTeams !== null && teams !== lastTeams) hostError.hidden = true;
    lastTeams = teams;
    const me = game.me();
    const byId = new Map(view.players.map((p) => [p.id, p]));
    const playerChip = (p) => {
      const isMe = p.id === view.player_id;
      return h(
        "li",
        { class: isMe ? "player me" : "player" },
        p.name,
        p.is_host ? h("span", { class: "tag" }, "host") : null,
        isMe ? h("span", { class: "tag" }, "you") : null,
      );
    };

    code.textContent = view.room_code;

    teamList.replaceChildren(
      ...view.teams.map((team) => {
        const full = team.player_ids.length >= view.settings.max_players_per_team;
        const mine = team.id === view.team_id;
        return h(
          "li",
          { class: mine ? "team mine" : "team", style: { "--team": team.color } },
          h(
            "div",
            { class: "team-head" },
            h("span", { class: "team-dot", "aria-hidden": "true" }),
            h("span", { class: "team-name" }, team.name),
            h("span", { class: "team-count" }, `${team.player_ids.length}/${view.settings.max_players_per_team}`),
            mine || full ? null : joinButton(team),
          ),
          h("ul", { class: "players" }, team.player_ids.map((id) => byId.get(id)).filter(Boolean).map(playerChip)),
        );
      }),
    );
    if (view.teams.length === 0) teamList.append(h("li", { class: "empty" }, "No teams yet. Make one below."));

    const loose = view.players.filter((p) => !p.team_id);
    unassigned.replaceChildren(
      ...(loose.length ? [h("h3", {}, "No team yet"), h("ul", { class: "players" }, loose.map(playerChip))] : []),
    );

    // Taken colors can't be picked; move the choice off one that was just taken.
    const taken = new Set(view.teams.map((t) => t.color.toLowerCase()));
    for (const input of swatches.querySelectorAll("input")) {
      input.disabled = taken.has(input.value.toLowerCase());
      input.parentElement.classList.toggle("taken", input.disabled);
    }
    const checked = swatches.querySelector("input:checked");
    if (!checked || checked.disabled) {
      const free = swatches.querySelector("input:not(:disabled)");
      if (free) free.checked = true;
    }

    const isHost = Boolean(me?.is_host);
    hostControls.hidden = !isHost;
    const host = view.players.find((p) => p.is_host);
    waitingNote.hidden = isHost;
    waitingNote.textContent = host ? `Waiting for ${host.name} to start the game…` : "Waiting for the host to start…";
  }

  return { update, unmount() {} };
}
