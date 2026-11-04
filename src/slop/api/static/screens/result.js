// Round result: what the prompt was, who got it, who wrote the script, and the
// scores. The whole room sees it for a few seconds, then whatever comes next.
//
// By the time this shows the next round has already started (or the game has
// ended) on the server, so `state.view` is what's next and `state.result` is the
// round that just ended. See `_showResult` in game.js.

import { h } from "../dom.js";

export function mount(root, game) {
  let mounted = true;
  let personalities = null;

  const room = h("p", { class: "eyebrow" });
  const prompt = h("p", { class: "role-name" });
  const winner = h("p", { class: "role-description" });
  const winnerTeam = h("p", { class: "note" });
  const personality = h("p", { class: "role-description" });
  const personalityHint = h("p", { class: "note" });
  const personalityGuess = h("p", { class: "note" });
  const scoreList = h("ul", { class: "teams" });
  const nextNote = h("p", { class: "my-team", role: "status" });
  const continueButton = h("button", { type: "button", class: "secondary", onclick: () => game.dismissResult() }, "Continue");

  root.append(
    h(
      "section",
      { class: "screen" },
      room,
      h("div", { class: "card host" }, h("h2", {}, "the prompt was"), prompt),
      h("div", { class: "card" }, h("h2", {}, "winning guess"), winner, winnerTeam),
      h("div", { class: "card" }, h("h2", {}, "written by"), personality, personalityHint, personalityGuess),
      h("h2", { class: "section-title" }, "scores"),
      scoreList,
      nextNote,
      continueButton,
    ),
  );

  function teamLabel(team) {
    return h(
      "span",
      { style: { "--team": team.color } },
      h("span", { class: "team-dot", "aria-hidden": "true" }, "■"),
      ` ${team.name}`,
    );
  }

  function showNext(state) {
    const { view, result } = state;
    const seconds = Math.max(0, Math.ceil((result.endsAt - Date.now()) / 1000));
    const round = view.current_round;
    const actingNext = view.teams.find((t) => t.id === round?.acting_team_id);
    let next = ["next round"];
    if (view.status === "finished") next = ["final scores"];
    else if (actingNext && view.tiebreaker?.first_round === round.round_number) next = ["tiebreaker! ", teamLabel(actingNext), " first"];
    else if (actingNext) next = ["next up: ", teamLabel(actingNext)];
    nextNote.replaceChildren("> ", ...next, ` in ${seconds}s`);
  }

  function update(state) {
    const { view, result } = state;
    if (!result) return;
    const name = (id) => personalities?.find((p) => p.id === id)?.name ?? id;

    room.textContent = `round over / room ${view.room_code}`;
    prompt.textContent = result.prompt ?? "???";

    const accepted = result.guesses.find((g) => g.accepted);
    const scorer = view.teams.find((t) => t.id === accepted?.team_id);
    winner.textContent = accepted ? `"${accepted.guess}"` : "nobody got it";
    winner.classList.toggle("picked", Boolean(accepted));
    winnerTeam.hidden = !scorer;
    winnerTeam.replaceChildren(...(scorer ? ["from ", teamLabel(scorer)] : []));

    const acting = view.teams.find((t) => t.id === result.acting_team_id);
    const right = result.personality_guess === result.personality_id;
    personality.textContent = name(result.personality_id) ?? "???";
    personalityHint.textContent = personalities?.find((p) => p.id === result.personality_id)?.description ?? "";
    personalityHint.hidden = !personalityHint.textContent;
    personalityGuess.textContent = `${acting?.name ?? "the acting team"} guessed ${name(result.personality_guess)}. ${right ? "correct!" : "nope."}`;

    const changes = result.score_changes ?? {};
    scoreList.replaceChildren(
      ...view.teams.map((team) =>
        h(
          "li",
          { class: team.id === view.team_id ? "team mine" : "team", style: { "--team": team.color } },
          h(
            "div",
            { class: "team-head" },
            h("span", { class: "team-dot", "aria-hidden": "true" }, "■"),
            h("span", { class: "team-name" }, team.name),
            h("span", { class: "team-count" }, `+${changes[team.id] ?? 0}`),
            h("span", { class: "team-score" }, `${team.score} ${team.score === 1 ? "pt" : "pts"}`),
          ),
        ),
      ),
    );

    showNext(state);
  }

  const ticker = setInterval(() => update(game.state), 1000);
  game.personalities().then(
    (list) => {
      personalities = list;
      if (mounted) update(game.state);
    },
    () => {}, // Falls back to the personality's id.
  );

  return {
    update,
    unmount() {
      mounted = false;
      clearInterval(ticker);
    },
  };
}
