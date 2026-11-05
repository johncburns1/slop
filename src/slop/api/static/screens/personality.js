// Personality pick: each team secretly picks the AI personality for the next team.
//
// Teams form a ring in the order they were formed (see `target_team` in
// src/slop/application/assign_personality.py). This screen shows only the pick
// your team makes. What your own team received stays secret until it's revealed.

import { attempt, errorBox, h } from "../dom.js";

export function mount(root, game) {
  const room = h("p", { class: "eyebrow" });
  const myTeam = h("p", { class: "my-team" });
  const summary = h("p", { class: "note", role: "status" });
  const target = h("div", { class: "team mine" });

  const loadingNote = h("p", { class: "note cursor" }, "loading personalities");
  const options = h("div", { class: "options stacked", role: "radiogroup", "aria-label": "Personality" });
  const confirmButton = h("button", { type: "submit", class: "primary" });
  const pickError = errorBox();
  const retryButton = h("button", { type: "button", class: "secondary", hidden: true }, "Try again");
  const confirmBar = h("div", { class: "confirm-bar", hidden: true }, confirmButton);

  const pickForm = h(
    "form",
    {
      class: "card",
      onsubmit: async (event) => {
        event.preventDefault();
        const id = options.querySelector("input:checked")?.value;
        if (id) await attempt(confirmButton, pickError, () => game.assignPersonality(id));
      },
    },
    h("h2", {}, "secret pick"),
    h("p", { class: "note" }, "you're picking for"),
    target,
    h("p", { class: "note" }, "anyone on your team can pick. the first confirm counts, so agree first."),
    loadingNote,
    options,
    retryButton,
    pickError,
    confirmBar,
  );

  const pickedTarget = h("div", { class: "team mine" });
  const pickedName = h("p", { class: "my-team" });
  const pickedHint = h("p", { class: "note" });
  const pickedCard = h(
    "div",
    { class: "card" },
    h("h2", {}, "your team's pick"),
    h("p", { class: "note" }, "your team picked for"),
    pickedTarget,
    pickedName,
    pickedHint,
    h("p", { class: "note" }, "only your team can see this. keep it quiet."),
  );

  const progress = h("ul", { class: "teams" });
  const waitingNote = h("p", { class: "note cursor" });

  root.append(
    h(
      "section",
      { class: "screen personality" },
      room,
      myTeam,
      summary,
      pickForm,
      pickedCard,
      h("h2", { class: "section-title" }, "who's picked"),
      progress,
      waitingNote,
    ),
  );

  let personalities = null;
  let loading = false;
  let mounted = true;

  async function load() {
    if (personalities || loading) return;
    loading = true;
    retryButton.hidden = true;
    const ok = await attempt(retryButton, pickError, async () => {
      personalities = await game.personalities();
    });
    loading = false;
    loadingNote.hidden = true;
    retryButton.hidden = ok;
    if (ok && mounted) {
      options.replaceChildren(...personalities.map(personalityOption));
      update(game.state);
    }
  }
  retryButton.addEventListener("click", load);

  function personalityOption(personality) {
    return h(
      "label",
      { class: "option" },
      h("input", {
        type: "radio",
        name: "personality",
        value: personality.id,
        onchange: () => {
          confirmButton.textContent = `Confirm ${personality.name}`;
          confirmBar.hidden = false;
          pickError.hidden = true;
        },
      }),
      h("span", { class: "option-label" }, personality.name),
      h("span", { class: "option-hint" }, personality.description),
    );
  }

  function teamHead(team, status) {
    return h(
      "div",
      { class: "team-head" },
      h("span", { class: "team-dot", "aria-hidden": "true" }, "■"),
      h("span", { class: "team-name" }, team.name),
      status,
    );
  }

  function showTeam(box, team) {
    box.style.setProperty("--team", team.color);
    box.replaceChildren(teamHead(team));
  }

  function update(state) {
    const view = state.view;
    if (state.connected) load();

    room.textContent = `room ${view.room_code}`;
    // A team with no players left is out of the ring, which closes up around it.
    const ring = view.teams.filter((t) => t.player_ids.length);

    const mine = view.teams.find((t) => t.id === view.team_id);
    myTeam.replaceChildren(
      ...(mine
        ? [h("span", { class: "team-dot", style: { "--team": mine.color } }, "■"), ` you're on ${mine.name}`]
        : []),
    );

    const pick = view.my_pick;
    pickForm.hidden = !mine || Boolean(pick);
    pickedCard.hidden = !pick;
    if (mine && !pick) showTeam(target, ring[(ring.indexOf(mine) + 1) % ring.length]);
    if (pick) {
      const team = view.teams.find((t) => t.id === pick.team_id);
      const personality = personalities?.find((p) => p.id === pick.personality_id);
      if (team) showTeam(pickedTarget, team);
      pickedName.textContent = `> ${personality?.name ?? pick.personality_id}`;
      pickedHint.textContent = personality?.description ?? "";
    }

    // Up top too: while picking, the full list below is a long scroll past the cards.
    summary.textContent = `> ${ring.filter((t) => t.has_picked).length}/${ring.length} teams have picked`;

    progress.replaceChildren(
      ...ring.map((team) =>
        h(
          "li",
          { class: team.id === view.team_id ? "team mine" : "team", style: { "--team": team.color } },
          teamHead(
            team,
            team.has_picked ? h("span", { class: "picked" }, "[x] picked") : h("span", { class: "team-count" }, "[ ] picking"),
          ),
        ),
      ),
    );

    waitingNote.hidden = !pick && Boolean(mine);
    const others = ring.filter((t) => !t.has_picked).map((t) => t.name);
    waitingNote.textContent = others.length
      ? `waiting for other teams: ${others.join(", ")}`
      : "everyone has picked. starting the game";
  }

  return {
    update,
    unmount() {
      mounted = false;
    },
  };
}
