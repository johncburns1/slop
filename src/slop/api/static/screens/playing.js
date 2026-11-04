// Playing: a round from its start until the personality guess that ends it.
//
// The acting team writes the prompt, reads the script from here while
// performing, picks the winning guess once guessing is over, and guesses who
// wrote the script. Everyone else sees who's acting and sends guesses. Everyone
// sees the time left to guess; the server keeps the deadline and says when it
// has passed. The server only sends the prompt and script to the acting team,
// so those parts stay empty for the rest.
// The round's result is its own screen: see result.js.

import { attempt, errorBox, h } from "../dom.js";

const MAX_PROMPT_WORDS = 6;
const TICK_MS = 250;
const URGENT_SECONDS = 10;
// The server closes guessing at zero. A phone that still hasn't heard by this long after asks it.
const RESYNC_AFTER_SECONDS = 3;
const SCRIPT_FAILED = "the AI couldn't write a script for that. try again, maybe with different words.";

export function mount(root, game) {
  let mounted = true;
  let writing = false;
  let lastRound = null;
  let seenFailures = 0;
  let personalities = null;
  let loadingPersonalities = false;
  let lastPhase = null;
  let resynced = false;

  const roundLabel = h("p", { class: "eyebrow" });
  const scoreboard = h("ul", { class: "scoreboard", "aria-label": "Scores" });
  const nextUp = h("p", { class: "note" });
  const countdownLabel = h("span", { class: "countdown-label" });
  const countdownTime = h("span", { class: "countdown-time" });
  const countdown = h("div", { class: "countdown", role: "timer", hidden: true }, countdownLabel, countdownTime);

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
  // Keeps the way to judging one tap away while reading a long script.
  const guessCount = h("p", { class: "note", "aria-live": "polite" });
  const endError = errorBox();
  const endButton = h(
    "button",
    {
      type: "button",
      class: "primary",
      onclick: () => attempt(endButton, endError, () => game.endGuessing()),
    },
    "We're done, judge now",
  );
  const scriptView = h(
    "div",
    { class: "screen" },
    roleCard,
    h("h2", { class: "section-title" }, "cast"),
    castList,
    h("h2", { class: "section-title" }, "script"),
    scriptLines,
    h("div", { class: "confirm-bar" }, guessCount, endError, endButton),
  );

  // Rows only ever get added, so a selected row stays selected while more guesses come in.
  const guessRows = h("div", { class: "options stacked" });
  const noGuessesNote = h("p", { class: "note" }, "no guesses came in");
  const nobodyRow = optionRow("winner", "nobody", "Nobody got it", "no points for the prompt", () => {
    chooseWinner("Confirm nobody got it");
  });
  const judgeButton = h("button", { type: "submit", class: "primary" });
  const judgeBar = h("div", { class: "confirm-bar", hidden: true }, judgeButton);
  const judgeError = errorBox();
  const judgeForm = h(
    "form",
    {
      class: "card host",
      onsubmit: async (event) => {
        event.preventDefault();
        const value = judgeForm.querySelector("input:checked")?.value;
        if (!value) return;
        await attempt(judgeButton, judgeError, () => game.pickWinningGuess(value === "nobody" ? null : Number(value)));
      },
    },
    h("h2", {}, "pick the winner"),
    h("p", { class: "note" }, "guessing is over. did anyone get it? close enough counts. anyone on your team can pick."),
    noGuessesNote,
    guessRows,
    nobodyRow,
    judgeError,
    judgeBar,
  );

  const personalityRows = h("div", { class: "options stacked", role: "radiogroup", "aria-label": "Personality" });
  const personalityLoading = h("p", { class: "note cursor" }, "loading personalities");
  const personalityRetry = h("button", { type: "button", class: "secondary", hidden: true, onclick: loadPersonalities }, "Try again");
  const personalityButton = h("button", { type: "submit", class: "primary" });
  const personalityBar = h("div", { class: "confirm-bar", hidden: true }, personalityButton);
  const personalityError = errorBox();
  const personalityForm = h(
    "form",
    {
      class: "card host",
      onsubmit: async (event) => {
        event.preventDefault();
        const id = personalityRows.querySelector("input:checked")?.value;
        if (id) await attempt(personalityButton, personalityError, () => game.guessPersonality(id));
      },
    },
    h("h2", {}, "who wrote your script?"),
    h("p", { class: "note" }, "a right guess is +1 for your team. the first confirm counts, so agree first."),
    personalityLoading,
    personalityRows,
    personalityRetry,
    personalityError,
    personalityBar,
  );

  const actingTeam = h("div", { class: "team" });
  const watchNote = h("h2", { role: "status" });
  const watchView = h("div", { class: "screen" }, actingTeam, watchNote);

  const guessInput = h("input", {
    id: "guess",
    placeholder: "what did they type?",
    autocomplete: "off",
    enterkeyhint: "send",
  });
  const guessButton = h("button", { type: "submit", class: "primary" }, "Send guess");
  const guessError = errorBox();
  const guessForm = h(
    "form",
    {
      class: "card host",
      onsubmit: async (event) => {
        event.preventDefault();
        const sent = await attempt(guessButton, guessError, () => game.submitGuess(guessInput.value));
        if (!sent) return;
        guessInput.value = "";
        guessInput.focus();
      },
    },
    h("h2", {}, "guess the prompt"),
    h("label", { for: "guess", class: "prompt" }, "your guess"),
    guessInput,
    h("p", { class: "note" }, "send as many as you like. the acting team picks the winner."),
    guessButton,
    guessError,
  );
  const myGuessList = h("ul", { class: "players" });
  const myGuesses = h("div", { class: "screen" }, h("h2", { class: "section-title" }, "your team's guesses"), myGuessList);

  // What the acting team decided, while it guesses the personality.
  const judgedNote = h("p", { class: "my-team", role: "status" });

  const betweenRounds = h("p", { class: "note cursor", role: "status" }, "next round coming up");

  root.append(
    h(
      "section",
      { class: "screen playing" },
      roundLabel,
      scoreboard,
      nextUp,
      countdown,
      promptForm,
      writingNote,
      scriptView,
      judgeForm,
      watchView,
      judgedNote,
      personalityForm,
      guessForm,
      myGuesses,
      betweenRounds,
    ),
  );

  function optionRow(name, value, label, hint, onchange) {
    return h(
      "label",
      { class: "option" },
      h("input", { type: "radio", name, value, onchange }),
      h("span", { class: "option-label" }, label),
      h("span", { class: "option-hint" }, hint),
    );
  }

  function chooseWinner(label) {
    judgeButton.textContent = label;
    judgeBar.hidden = false;
    judgeError.hidden = true;
  }

  function showGuessesToJudge(view, round) {
    for (let i = guessRows.children.length; i < round.guesses.length; i++) {
      const { guess, team_id: teamId } = round.guesses[i];
      guessRows.append(
        optionRow("winner", String(i), guess, view.teams.find((t) => t.id === teamId)?.name ?? "", () => {
          chooseWinner("Confirm this guess");
        }),
      );
    }
    noGuessesNote.hidden = round.guesses.length > 0;
  }

  /** Runs on every tick as well as every update, so it shows the time left as it goes. */
  function showCountdown() {
    const round = game.state.view?.current_round;
    const running = round?.phase === "guessing" && Boolean(round.guess_deadline);
    countdown.hidden = !running;
    if (!running) return;
    const left = game.guessSecondsLeft(round);
    const seconds = Math.max(0, Math.ceil(left));
    countdownLabel.textContent = seconds > 0 ? "time left" : "time's up";
    countdownTime.textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
    countdown.classList.toggle("urgent", seconds <= URGENT_SECONDS);
    if (left < -RESYNC_AFTER_SECONDS && !resynced && game.state.connected) {
      resynced = true;
      game.resync().catch(() => {});
    }
  }

  function showMyGuesses(view, round) {
    const mine = round.guesses.filter((g) => g.team_id === view.team_id);
    myGuesses.hidden = mine.length === 0;
    myGuessList.replaceChildren(
      ...mine.map((g, i) =>
        h(
          "li",
          { class: g.accepted ? "player me" : "player" },
          h("span", { class: "branch", "aria-hidden": "true" }, i === mine.length - 1 ? "└─ " : "├─ "),
          g.guess,
          g.accepted ? h("span", { class: "tag" }, " <winner>") : null,
        ),
      ),
    );
  }

  function showJudged(view, round) {
    const winner = round.guesses.find((g) => g.accepted);
    const team = view.teams.find((t) => t.id === winner?.team_id);
    judgedNote.replaceChildren(
      ...(winner && team ? [`> winning guess: "${winner.guess}" from `, teamName(team)] : ["> nobody got it"]),
    );
  }

  async function loadPersonalities() {
    if (personalities || loadingPersonalities) return;
    loadingPersonalities = true;
    personalityRetry.hidden = true;
    const ok = await attempt(personalityRetry, personalityError, async () => {
      personalities = await game.personalities();
    });
    loadingPersonalities = false;
    personalityLoading.hidden = true;
    personalityRetry.hidden = ok;
    if (!ok || !mounted) return;
    personalityRows.replaceChildren(
      ...personalities.map((p) =>
        optionRow("personality", p.id, p.name, p.description, () => {
          personalityButton.textContent = `Confirm ${p.name}`;
          personalityBar.hidden = false;
          personalityError.hidden = true;
        }),
      ),
    );
  }

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
    const notes = {
      waiting_for_prompt: "> they're writing their script",
      guessing: "> the script is ready. watch them perform!",
      judging: "> guessing is over. they're picking the winner",
      guessing_personality: "> they're guessing who wrote their script",
    };
    watchNote.textContent = notes[round.phase];
    watchNote.classList.toggle("cursor", round.phase !== "guessing");
  }

  function update(state) {
    const view = state.view;
    const round = view.current_round;

    // A new round starts with an empty prompt box.
    if (round?.round_number !== lastRound) {
      lastRound = round?.round_number ?? null;
      promptInput.value = "";
      promptError.hidden = true;
      guessInput.value = "";
      guessError.hidden = true;
      guessRows.replaceChildren();
      judgeForm.reset();
      judgeBar.hidden = true;
      judgeError.hidden = true;
      personalityForm.reset();
      personalityBar.hidden = true;
      personalityError.hidden = true;
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
    const guessing = round?.phase === "guessing";
    const judging = round?.phase === "judging";
    const judged = round?.phase === "guessing_personality";
    const needsPrompt = round && acting && !judged && !round.script;
    promptForm.hidden = !needsPrompt || writing;
    writingNote.hidden = !needsPrompt || !writing;
    scriptView.hidden = !acting || !guessing || !round.script;
    judgeForm.hidden = !acting || !judging;
    countdown.classList.toggle("big", !acting);
    watchView.hidden = !round || acting;
    judgedNote.hidden = !judged;
    personalityForm.hidden = !acting || !judged;
    guessForm.hidden = !round || acting || !guessing || !view.team_id;
    myGuesses.hidden = !round || acting;
    betweenRounds.hidden = Boolean(round);
    showCountdown();
    // The script is gone when guessing ends, so don't leave the phone scrolled down past the form.
    if (judging && lastPhase === "guessing") window.scrollTo(0, 0);
    if (round?.phase !== lastPhase) resynced = false;
    lastPhase = round?.phase ?? null;

    if (!round) return;
    if (!acting) showWatching(view, round);
    else if (round.script && !judged) showScript(view, round);
    if (acting && judging) showGuessesToJudge(view, round);
    if (acting && guessing) {
      const count = round.guesses.length;
      guessCount.textContent = `${count} ${count === 1 ? "guess" : "guesses"} so far`;
    }
    if (!acting) showMyGuesses(view, round);
    if (judged) showJudged(view, round);
    if (acting && judged && state.connected) loadPersonalities();
  }

  const ticker = setInterval(showCountdown, TICK_MS);

  function refresh() {
    if (mounted) update(game.state);
  }

  return {
    update,
    unmount() {
      mounted = false;
      clearInterval(ticker);
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
