// Home: join a game with a room code, or start a new one.

import { attempt, errorBox, h } from "../dom.js";

const NAME_KEY = "slop.name";
const ROUND_CHOICES = [1, 2, 3, 4, 5];
const DEFAULT_ROUNDS = 3;

const LOGO = String.raw` ____  _     ___  ____
/ ___|| |   / _ \|  _ \
\___ \| |  | | | | |_) |
 ___) | |__| |_| |  __/
|____/|_____\___/|_|`;
// Slop dripping off the logo.
const DRIPS = String.raw`  ' :   |    :    ;
  .     '         '
        .`;

export function mount(root, game) {
  const roomFromLink = new URLSearchParams(location.search).get("room") ?? "";

  const name = h("input", {
    id: "player-name",
    autocomplete: "nickname",
    maxlength: 20,
    placeholder: "your name",
    value: localStorage.getItem(NAME_KEY) ?? "",
  });
  const room = h("input", {
    id: "room-code",
    class: "code-input",
    autocomplete: "off",
    autocapitalize: "characters",
    spellcheck: "false",
    maxlength: 6,
    placeholder: "____",
    value: roomFromLink.toUpperCase(),
    oninput: () => (room.value = room.value.toUpperCase()),
  });
  const joinButton = h("button", { type: "submit", class: "primary" }, "Join game");
  const joinError = errorBox();

  const tones = h(
    "div",
    { class: "options", role: "radiogroup", "aria-label": "Content setting" },
    toneOption("family", "family", "clean fun, all ages", true),
    toneOption("adult", "adult", "anything goes", false),
  );
  const rounds = h(
    "div",
    { class: "segments", role: "radiogroup", "aria-labelledby": "rounds-label" },
    ROUND_CHOICES.map((count) => roundsOption(count)),
  );
  const createButton = h("button", { type: "submit", class: "secondary" }, "Create game");
  const createError = errorBox();

  function playerName(errors) {
    localStorage.setItem(NAME_KEY, name.value.trim());
    if (name.value.trim()) return name.value;
    errors.textContent = "enter your name first";
    errors.hidden = false;
    name.focus();
    return null;
  }

  const joinForm = h(
    "form",
    {
      class: "card",
      onsubmit: async (event) => {
        event.preventDefault();
        const player = playerName(joinError);
        if (player) await attempt(joinButton, joinError, () => game.join(room.value, player));
      },
    },
    h("h2", {}, "join a game"),
    h("label", { for: "room-code", class: "prompt" }, "room code"),
    room,
    joinButton,
    joinError,
  );

  const createForm = h(
    "form",
    {
      class: "card",
      onsubmit: async (event) => {
        event.preventDefault();
        const player = playerName(createError);
        const tone = tones.querySelector("input:checked").value;
        const roundsPerTeam = Number(rounds.querySelector("input:checked").value);
        if (player) await attempt(createButton, createError, () => game.createAndJoin(tone, roundsPerTeam, player));
      },
    },
    h("h2", {}, "new game"),
    tones,
    h("span", { id: "rounds-label", class: "prompt segments-label" }, "rounds per team"),
    rounds,
    createButton,
    createError,
  );

  root.append(
    h(
      "section",
      { class: "screen home" },
      h(
        "header",
        { class: "brand" },
        h(
          "h1",
          { "aria-label": "Slop" },
          h("pre", { class: "logo", "aria-hidden": "true" }, LOGO),
          h("pre", { class: "drips", "aria-hidden": "true" }, DRIPS),
        ),
        h("p", { class: "tagline" }, "act out what the AI wrote. guess the prompt."),
      ),
      h("div", { class: "field" }, h("label", { for: "player-name", class: "prompt" }, "name"), name),
      joinForm,
      h("p", { class: "or", "aria-hidden": "true" }, "-- or --"),
      createForm,
    ),
  );
  (roomFromLink && name.value ? joinButton : name.value ? room : name).focus();

  return { update() {}, unmount() {} };
}

function toneOption(value, label, hint, checked) {
  return h(
    "label",
    { class: "option" },
    h("input", { type: "radio", name: "content-tone", value, checked }),
    h("span", { class: "option-label" }, label),
    h("span", { class: "option-hint" }, hint),
  );
}

function roundsOption(count) {
  return h(
    "label",
    { class: "segment" },
    h("input", { type: "radio", name: "rounds-per-team", value: count, checked: count === DEFAULT_ROUNDS }),
    h("span", {}, String(count)),
  );
}
