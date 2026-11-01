// Home: join a game with a room code, or start a new one.

import { attempt, errorBox, h } from "../dom.js";

const NAME_KEY = "slop.name";

export function mount(root, game) {
  const roomFromLink = new URLSearchParams(location.search).get("room") ?? "";

  const name = h("input", {
    id: "player-name",
    autocomplete: "nickname",
    maxlength: 20,
    placeholder: "What should we call you?",
    value: localStorage.getItem(NAME_KEY) ?? "",
  });
  const room = h("input", {
    id: "room-code",
    class: "code-input",
    autocomplete: "off",
    autocapitalize: "characters",
    spellcheck: "false",
    maxlength: 6,
    placeholder: "ABCD",
    value: roomFromLink.toUpperCase(),
    oninput: () => (room.value = room.value.toUpperCase()),
  });
  const joinButton = h("button", { type: "submit", class: "primary" }, "Join game");
  const joinError = errorBox();

  const tones = h(
    "div",
    { class: "segmented", role: "radiogroup", "aria-label": "Content setting" },
    toneOption("family", "Family", "Clean fun for all ages", true),
    toneOption("adult", "Adult", "Anything goes", false),
  );
  const createButton = h("button", { type: "submit", class: "secondary" }, "Create game");
  const createError = errorBox();

  function playerName(errors) {
    localStorage.setItem(NAME_KEY, name.value.trim());
    if (name.value.trim()) return name.value;
    errors.textContent = "Enter your name first";
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
    h("h2", {}, "Join a game"),
    h("label", { for: "room-code" }, "Room code"),
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
        if (player) await attempt(createButton, createError, () => game.createAndJoin(tone, player));
      },
    },
    h("h2", {}, "Start a new game"),
    tones,
    createButton,
    createError,
  );

  root.append(
    h(
      "section",
      { class: "screen home" },
      h("header", { class: "brand" }, h("h1", {}, "Slop"), h("p", {}, "Act out what the AI wrote. Guess the prompt.")),
      h("div", { class: "field" }, h("label", { for: "player-name" }, "Your name"), name),
      joinForm,
      h("p", { class: "or" }, "or"),
      createForm,
    ),
  );
  (roomFromLink && name.value ? joinButton : name.value ? room : name).focus();

  return { update() {}, unmount() {} };
}

function toneOption(value, label, hint, checked) {
  return h(
    "label",
    { class: "segment" },
    h("input", { type: "radio", name: "content-tone", value, checked }),
    h("span", { class: "segment-label" }, label),
    h("span", { class: "segment-hint" }, hint),
  );
}
