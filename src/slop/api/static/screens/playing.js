// Playing: a round from its start until the script is ready.
//
// The acting team writes the prompt and then reads the script from here while
// performing. Everyone else sees who's acting. The server only ever sends the
// prompt and script to the acting team, so those parts stay empty for the rest.
//
// Slice 3b adds guessing, judging, and the personality reveal: see `laterPhase`.

import { attempt, errorBox, h } from "../dom.js";

const MAX_PROMPT_WORDS = 6;
const SCRIPT_FAILED = "the AI couldn't write a script for that. try again, maybe with different words.";

export function mount(root, game) {
  let mounted = true;
  let writing = false;
  let lastRound = null;
  let seenFailures = 0;

  const roundLabel = h("p", { class: "eyebrow" });
  const scoreboard = h("ul", { class: "scoreboard", "aria-label": "Scores" });
  const nextUp = h("p", { class: "note" });

  const promptInput = h("textarea", {
    id: "prompt",
    class: "prompt-box",
    rows: 2,
    placeholder: "your prompt",
    autocomplete: "off",
    enterkeyhint: "send",
    oninput: () => showWordCount(),
    onkeydown: (event) => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        promptForm.requestSubmit();
      }
    },
  });
  const wordCount = h("p", { class: "word-count", "aria-live": "polite" });
  const submitButton = h("button", { type: "submit", class: "primary" }, "Write our script");
  const promptError = errorBox();
  const promptForm = h(
    "form",
    {
      class: "card host",
      onsubmit: async (event) => {
        event.preventDefault();
        writing = true;
        refresh();
        await attempt(submitButton, promptError, () => game.submitPrompt(promptInput.value));
        writing = false;
        refresh();
      },
    },
    h("h2", {}, "you're up"),
    h("label", { for: "prompt", class: "prompt" }, `write 1 to ${MAX_PROMPT_WORDS} words`),
    promptInput,
    wordCount,
    h("p", { class: "note" }, "anyone on your team can send it, so agree first. the other teams will guess these words."),
    submitButton,
    promptError,
  );
  const writingNote = h("h2", { class: "cursor", role: "status" }, "writing your script");

  const roleCard = h("div", { class: "card host" });
  const castList = h("ul", { class: "players" });
  const scriptLines = h("div", { class: "script" });
  const scriptView = h(
    "div",
    { class: "screen" },
    roleCard,
    h("h2", { class: "section-title" }, "cast"),
    castList,
    h("h2", { class: "section-title" }, "script"),
    scriptLines,
  );

  const actingTeam = h("div", { class: "team" });
  const watchNote = h("h2", { role: "status" });
  const watchView = h("div", { class: "screen" }, actingTeam, watchNote);

  // Where slice 3b's guessing, judging, and reveal screens go.
  const laterPhase = h("p", { class: "note cursor", role: "status" });

  root.append(
    h(
      "section",
      { class: "screen playing" },
      roundLabel,
      scoreboard,
      nextUp,
      promptForm,
      writingNote,
      scriptView,
      watchView,
      laterPhase,
    ),
  );

  function showWordCount() {
    const count = countWords(promptInput.value);
    wordCount.textContent = `${count}/${MAX_PROMPT_WORDS} words`;
    wordCount.classList.toggle("over", count > MAX_PROMPT_WORDS);
  }

  function scoreChip(view, team, round) {
    const classes = ["score", team.id === view.team_id ? "mine" : "", team.id === round?.acting_team_id ? "acting" : ""];
    return h(
      "li",
      { class: classes.join(" ").trim(), style: { "--team": team.color } },
      h("span", { class: "team-dot", "aria-hidden": "true" }, "■"),
      h("span", { class: "team-name" }, team.name),
      h("span", { class: "team-score" }, String(team.score)),
    );
  }

  function teamName(team) {
    return h(
      "span",
      { style: { "--team": team.color } },
      h("span", { class: "team-dot", "aria-hidden": "true" }, "■"),
      ` ${team.name}`,
    );
  }

  function showNext(view) {
    nextUp.hidden = !view.current_round;
    if (!view.current_round) return;
    const next = nextTeam(view);
    nextUp.replaceChildren("next up: ", next ? teamName(next) : "final scores, or a tiebreaker");
  }

  function showScript(view, round) {
    const script = round.script;
    const myRole = script.roles.find((r) => r.player_id === view.player_id);
    roleCard.replaceChildren(
      h("h2", {}, "your role"),
      h("p", { class: "role-name" }, myRole ? myRole.name : "no role this time"),
      myRole ? h("p", { class: "role-description" }, myRole.description) : null,
      h("p", { class: "note" }, `your prompt: "${round.prompt}". don't say it out loud!`),
    );
    const byId = new Map(view.players.map((p) => [p.id, p]));
    castList.replaceChildren(
      ...script.roles.map((role, i) =>
        h(
          "li",
          { class: role === myRole ? "player me" : "player" },
          h("span", { class: "branch", "aria-hidden": "true" }, i === script.roles.length - 1 ? "└─ " : "├─ "),
          `${role.name}: ${byId.get(role.player_id)?.name ?? "nobody"}`,
          role === myRole ? h("span", { class: "tag" }, " <you>") : null,
        ),
      ),
    );
    scriptLines.replaceChildren(
      ...script.content
        .split("\n")
        .filter((line) => line.trim())
        .map((line) => h("p", { class: myRole && line.startsWith(`${myRole.name}:`) ? "my-line" : null }, line)),
    );
  }

  function showWatching(view, round) {
    const team = view.teams.find((t) => t.id === round.acting_team_id);
    const byId = new Map(view.players.map((p) => [p.id, p]));
    const names = (team?.player_ids ?? []).map((id) => byId.get(id)?.name).filter(Boolean);
    actingTeam.style.setProperty("--team", team?.color ?? "");
    actingTeam.replaceChildren(
      h("p", { class: "eyebrow" }, "now acting"),
      h(
        "div",
        { class: "team-head" },
        h("span", { class: "team-dot", "aria-hidden": "true" }, "■"),
        h("span", { class: "team-name" }, team?.name ?? ""),
      ),
      h("p", { class: "note" }, names.join(", ")),
    );
    const ready = round.phase !== "waiting_for_prompt";
    watchNote.textContent = ready ? "> the script is ready. watch them perform!" : "> they're writing their script";
    watchNote.classList.toggle("cursor", !ready);
  }

  function update(state) {
    const view = state.view;
    const round = view.current_round;

    // A new round starts with an empty prompt box.
    if (round?.round_number !== lastRound) {
      lastRound = round?.round_number ?? null;
      promptInput.value = "";
      promptError.hidden = true;
    }
    // Only the acting team hears about a failed script, and the submit's ack is still a success.
    const failures = round?.script_failures ?? 0;
    if (failures > seenFailures) {
      promptError.textContent = SCRIPT_FAILED;
      promptError.hidden = false;
    }
    seenFailures = failures;

    roundLabel.textContent = `${round ? roundText(view) : "between rounds"} / room ${view.room_code}`;
    scoreboard.replaceChildren(...view.teams.map((team) => scoreChip(view, team, round)));
    showNext(view);
    showWordCount();

    const acting = round?.acting_team_id === view.team_id;
    const later = !round || round.phase === "guessing_personality";
    const needsPrompt = acting && !later && !round.script;
    promptForm.hidden = !needsPrompt || writing;
    writingNote.hidden = !needsPrompt || !writing;
    scriptView.hidden = !acting || later || !round.script;
    watchView.hidden = acting || later;
    laterPhase.hidden = !later;
    laterPhase.textContent = round ? "the next part of this round is coming soon. keep this page open." : "next round coming up";

    if (later) return;
    if (!acting) showWatching(view, round);
    else if (round.script) showScript(view, round);
  }

  function refresh() {
    if (mounted) update(game.state);
  }

  return {
    update,
    unmount() {
      mounted = false;
    },
  };
}

/** Words the way the server counts them: anything between runs of whitespace. */
function countWords(text) {
  return text.trim() ? text.trim().split(/\s+/).length : 0;
}

/** "round 2 of 6", or for a tiebreaker "tiebreaker 1: round 1 of 2". */
function roundText(view) {
  const number = view.current_round.round_number;
  const tiebreaker = view.tiebreaker;
  if (tiebreaker && number >= tiebreaker.first_round) {
    const turn = number - tiebreaker.first_round + 1;
    return `tiebreaker ${tiebreaker.cycle}: round ${turn} of ${tiebreaker.team_ids.length}`;
  }
  return `round ${number + 1} of ${view.teams.length * view.settings.rounds_per_team}`;
}

/**
 * The team that acts after this round, or null if that depends on the scores.
 * The server's rule: teams take turns in order until the regular rounds run
 * out, then a tiebreaker's teams act in its order (`next_step` in game_end.py).
 */
function nextTeam(view) {
  const number = view.current_round.round_number;
  const tiebreaker = view.tiebreaker;
  if (tiebreaker && number >= tiebreaker.first_round) {
    const nextId = tiebreaker.team_ids[number - tiebreaker.first_round + 1];
    return view.teams.find((t) => t.id === nextId) ?? null;
  }
  const following = number + 1;
  if (following >= view.teams.length * view.settings.rounds_per_team) return null;
  return view.teams[following % view.teams.length];
}
