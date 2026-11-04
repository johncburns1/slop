// Finished: the winner (or a draw), the final scores, and the awards, then
// the host's play again.

import { asciiBox, attempt, errorBox, h } from "../dom.js";

export function mount(root, game) {
  const verdict = h("pre", { class: "room-code" });
  const headline = h("h2", { class: "headline" });
  const myResult = h("p", { class: "note" });
  const scoreList = h("ul", { class: "teams" });
  const awardList = h("ul", { class: "awards" });
  const awardsCard = h("div", { class: "card" }, h("h2", {}, "awards"), awardList);

  const playAgainButton = h("button", { type: "button", class: "primary" }, "Play again");
  const hostError = errorBox();
  playAgainButton.addEventListener("click", () => attempt(playAgainButton, hostError, () => game.playAgain()));
  const hostControls = h(
    "div",
    { class: "card host" },
    h("h2", {}, "sudo"),
    h("p", { class: "note" }, "you're the host. same players, same teams, scores back to zero."),
    playAgainButton,
    hostError,
  );
  const waitingNote = h("p", { class: "note cursor" });

  const leaveButton = h("button", { type: "button", class: "secondary" }, "Leave");
  leaveButton.addEventListener("click", () => {
    if (confirm("Leave this game?")) game.exit();
  });

  root.append(
    h(
      "section",
      { class: "screen" },
      h("p", { class: "eyebrow" }, "game over"),
      verdict,
      headline,
      myResult,
      h("h2", { class: "section-title" }, "final scores"),
      scoreList,
      awardsCard,
      hostControls,
      waitingNote,
      leaveButton,
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

  function update(state) {
    const view = state.view;
    const me = game.me();
    const ranked = [...view.teams].sort((a, b) => b.score - a.score);
    // The server's rule: a sole leader wins, and a tie that's still standing at the end is a draw.
    const leaders = ranked.filter((t) => t.score === ranked[0]?.score);
    const winner = leaders.length === 1 ? leaders[0] : null;

    verdict.textContent = asciiBox(winner ? "WINNER" : "DRAW");
    if (winner) {
      headline.replaceChildren(teamLabel(winner), ` wins with ${winner.score} ${points(winner.score)}`);
      myResult.textContent = winner.id === view.team_id ? "> that's your team. take a bow." : "";
    } else {
      const names = leaders.flatMap((t, i) => (i === 0 ? [teamLabel(t)] : [" + ", teamLabel(t)]));
      headline.replaceChildren(...names, ` tie on ${leaders[0]?.score ?? 0} ${points(leaders[0]?.score ?? 0)}`);
      myResult.textContent = "> the tiebreakers ran out. share the glory.";
    }
    myResult.hidden = !myResult.textContent;

    scoreList.replaceChildren(
      ...ranked.map((team) => {
        // Tied teams share a rank: 1, 2, 2, 4.
        const rank = ranked.findIndex((t) => t.score === team.score) + 1;
        return h(
          "li",
          { class: team.id === view.team_id ? "team mine" : "team", style: { "--team": team.color } },
          h(
            "div",
            { class: "team-head" },
            h("span", { class: "team-count" }, `#${rank}`),
            h("span", { class: "team-dot", "aria-hidden": "true" }, "■"),
            h("span", { class: "team-name" }, team.name),
            h("span", { class: "team-score" }, `${team.score} ${points(team.score)}`),
          ),
        );
      }),
    );

    // Awards can come a moment after the scores, or not at all.
    awardsCard.hidden = view.awards.length === 0;
    awardList.replaceChildren(
      ...view.awards.map((award) =>
        h(
          "li",
          {},
          h("p", { class: "award-title" }, award.title),
          h("p", { class: "award-recipient" }, award.recipient),
          h("p", { class: "note" }, award.reason),
        ),
      ),
    );

    const isHost = Boolean(me?.is_host);
    hostControls.hidden = !isHost;
    const host = view.players.find((p) => p.is_host);
    waitingNote.hidden = isHost;
    waitingNote.textContent = `waiting to see if ${host ? host.name : "the host"} plays again`;
  }

  return { update, unmount() {} };
}

function points(score) {
  return score === 1 ? "pt" : "pts";
}
