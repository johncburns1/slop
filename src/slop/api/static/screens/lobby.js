// Lobby: the room code, who's here, and forming teams until the host starts.

import { attempt, errorBox, h, roomCodeBox, setRoomCode } from "../dom.js";

const TEAM_COLORS = ["#E53935", "#1E88E5", "#43A047", "#FDD835", "#8E24AA", "#FB8C00", "#00ACC1", "#D81B60"];

export function mount(root, game) {
  const code = roomCodeBox();
  const roundsNote = h("p", { class: "note" });
  const leaveButton = h("button", { type: "button", class: "link" }, "exit");
  const leaveError = errorBox();
  leaveButton.addEventListener("click", () => {
    if (confirm("Leave this game?")) attempt(leaveButton, leaveError, () => game.leave());
  });

  const teamList = h("ul", { class: "teams" });
  const teamError = errorBox();
  const unassigned = h("div", { class: "unassigned" });

  const teamName = h("input", { id: "team-name", maxlength: 20, placeholder: "team name", autocomplete: "off" });
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
    h("h2", {}, "new team"),
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
  const hostControls = h(
    "div",
    { class: "card host" },
    h("h2", {}, "sudo"),
    h("p", { class: "note" }, "you're the host. you start the game."),
    shuffleButton,
    startButton,
    hostError,
  );
  const waitingNote = h("p", { class: "note cursor" });

  root.append(
    h(
      "section",
      { class: "screen lobby" },
      h("header", { class: "lobby-header" }, h("p", { class: "eyebrow" }, "room code"), leaveButton),
      code,
      roundsNote,
      leaveError,
      h("h2", { class: "section-title" }, "teams"),
      teamList,
      teamError,
      unassigned,
      createForm,
      hostControls,
      waitingNote,
    ),
  );

  function joinButton(team) {
    const button = h("button", { type: "button", class: "small" }, "join");
    button.addEventListener("click", () => attempt(button, teamError, () => game.joinTeam(team.id)));
    return button;
  }

  // Players as a file tree: ├─ ana <host> / └─ ben <you>
  function playerTree(view, players) {
    return h(
      "ul",
      { class: "players" },
      players.map((p, i) => {
        const isMe = p.id === view.player_id;
        return h(
          "li",
          { class: isMe ? "player me" : "player" },
          h("span", { class: "branch", "aria-hidden": "true" }, i === players.length - 1 ? "└─ " : "├─ "),
          p.name,
          p.is_host ? h("span", { class: "tag" }, " <host>") : null,
          isMe ? h("span", { class: "tag" }, " <you>") : null,
        );
      }),
    );
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
    const max = view.settings.max_players_per_team;

    setRoomCode(code, view.room_code);
    const rounds = view.settings.rounds_per_team;
    roundsNote.textContent = `${rounds} ${rounds === 1 ? "round" : "rounds"} each`;

    teamList.replaceChildren(
      ...view.teams.map((team) => {
        const mine = team.id === view.team_id;
        const full = team.player_ids.length >= max;
        return h(
          "li",
          { class: mine ? "team mine" : "team", style: { "--team": team.color } },
          h(
            "div",
            { class: "team-head" },
            h("span", { class: "team-dot", "aria-hidden": "true" }, "■"),
            h("span", { class: "team-name" }, team.name),
            h("span", { class: "team-count" }, `${team.player_ids.length}/${max}`),
            mine || full ? null : joinButton(team),
          ),
          playerTree(view, team.player_ids.map((id) => byId.get(id)).filter(Boolean)),
        );
      }),
    );
    if (view.teams.length === 0) teamList.append(h("li", { class: "empty" }, "no teams yet. make one below."));

    const loose = view.players.filter((p) => !p.team_id);
    unassigned.replaceChildren(...(loose.length ? [h("h3", {}, "no team yet"), playerTree(view, loose)] : []));

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
    waitingNote.textContent = `waiting for ${host ? host.name : "the host"} to start the game`;
  }

  return { update, unmount() {} };
}
