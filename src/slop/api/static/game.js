// The socket and state layer: talks to the server and keeps this phone's view of the game.
//
// It speaks exactly the message contract in src/slop/api/messages.py. The
// state is the `rejoin_game` reply (the "player view"), kept up to date by
// applying the game events the server sends. Screens read `game.state`,
// call the action methods, and re-render on `game.subscribe(...)`.
//
// The session (room code + player id) is kept in localStorage, so a reloaded
// or reconnected phone sends `rejoin_game` and lands back where it was.

import { io } from "./vendor/socket.io.esm.min.js";

const SESSION_KEY = "slop.session";
const ACK_TIMEOUT_MS = 10000;

/** A message the server rejected. `code` and `message` come from its error reply. */
export class GameError extends Error {
  constructor(code, message, request) {
    super(message);
    this.code = code;
    this.request = request;
  }
}

function isErrorReply(reply) {
  return reply !== null && typeof reply === "object" && typeof reply.code === "string" && "request" in reply;
}

function loadSession() {
  try {
    const session = JSON.parse(localStorage.getItem(SESSION_KEY));
    return session && session.roomCode && session.playerId ? session : null;
  } catch {
    return null;
  }
}

function saveSession(session) {
  if (session) localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  else localStorage.removeItem(SESSION_KEY);
}

// How each game event changes the player view. Events not listed here don't
// change anything the current screens show; later slices add their own.
const reducers = {
  PlayerJoined(view, e) {
    const isHost = view.players.length === 0;
    view.players.push({ id: e.player_id, name: e.player_name, team_id: null, is_host: isHost });
  },
  PlayerLeft(view, e) {
    view.players = view.players.filter((p) => p.id !== e.player_id);
    for (const team of view.teams) team.player_ids = team.player_ids.filter((id) => id !== e.player_id);
  },
  TeamFormed(view, e) {
    view.teams.push({
      id: e.team_id,
      name: e.team_name,
      color: e.color,
      player_ids: [],
      score: 0,
      has_picked: false,
      personality_id: null,
    });
  },
  PlayerJoinedTeam(view, e) {
    for (const team of view.teams) team.player_ids = team.player_ids.filter((id) => id !== e.player_id);
    view.teams.find((t) => t.id === e.team_id)?.player_ids.push(e.player_id);
    const player = view.players.find((p) => p.id === e.player_id);
    if (player) player.team_id = e.team_id;
    if (e.player_id === view.player_id) view.team_id = e.team_id;
  },
  TeamDisbanded(view, e) {
    view.teams = view.teams.filter((t) => t.id !== e.team_id);
    for (const player of view.players) if (player.team_id === e.team_id) player.team_id = null;
    if (view.team_id === e.team_id) view.team_id = null;
  },
  PersonalitySelectionStarted(view) {
    view.status = "personality_selection";
  },
  GameCompleted(view, e) {
    view.status = "finished";
    view.current_round = null;
    for (const team of view.teams) team.score = e.final_scores[team.id] ?? team.score;
  },
  AwardsGiven(view, e) {
    view.awards = e.awards;
  },
  GameRestarted(view) {
    view.status = "personality_selection";
    view.current_round = null;
    view.my_pick = null;
    view.awards = [];
    for (const team of view.teams) Object.assign(team, { score: 0, has_picked: false, personality_id: null });
  },
};

class Game {
  constructor() {
    // view: the player view, or null when not in a game.
    // connected: whether the socket is up (null before the first try).
    // restoring: a rejoin of the saved session is in flight.
    this.state = { view: null, connected: null, restoring: false };
    this._session = loadSession();
    this._listeners = new Set();
    this._socket = io({ transports: ["websocket", "polling"] });
    this._socket.on("connect", () => this._onConnect());
    this._socket.on("disconnect", () => this._set({ connected: false }));
    this._socket.on("connect_error", () => this._set({ connected: false }));
    // Rejections also come back in the ack, which is where the screens handle them.
    this._socket.on("error", () => {});
    this._socket.onAny((name, payload) => this._apply(name, payload));
    if (this._session) this.state.restoring = true;
  }

  /** Call `listener(state)` on every change. Returns a function that unsubscribes. */
  subscribe(listener) {
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  /** The current player, or undefined. */
  me() {
    const view = this.state.view;
    return view?.players.find((p) => p.id === view.player_id);
  }

  async createAndJoin(contentTone, playerName) {
    const { room_code } = await this._send("create_game", { content_tone: contentTone });
    await this.join(room_code, playerName);
  }

  async join(roomCode, playerName) {
    const room = roomCode.trim().toUpperCase();
    const { player_id } = await this._send("join_game", { room_code: room, player_name: playerName });
    this._session = { roomCode: room, playerId: player_id };
    saveSession(this._session);
    // join_game only acks ids; rejoin_game on the same connection returns the full view.
    await this._rejoin();
  }

  async leave() {
    try {
      await this._send("leave_game", {});
    } finally {
      this._forget();
    }
  }

  /**
   * Leave a game that has started. The server keeps its players from then on
   * and rejects `leave_game`, so this only forgets the game on this phone.
   */
  exit() {
    this._forget();
  }

  createTeam(teamName, color) {
    return this._send("create_team", { team_name: teamName, color });
  }

  joinTeam(teamId) {
    return this._send("join_team", { team_id: teamId });
  }

  shuffleTeams() {
    return this._send("shuffle_teams", {});
  }

  startPersonalitySelection() {
    return this._send("start_personality_selection", {});
  }

  playAgain() {
    return this._send("play_again", {});
  }

  async _onConnect() {
    this._set({ connected: true });
    if (!this._session) return;
    try {
      await this._rejoin();
    } catch (error) {
      // The game expired or we're no longer in it: start again from home.
      if (error instanceof GameError && error.code !== "rate_limited") this._forget();
      else this._set({ restoring: false });
    }
  }

  async _rejoin() {
    const view = await this._send("rejoin_game", {
      room_code: this._session.roomCode,
      player_id: this._session.playerId,
    });
    this._set({ view, restoring: false });
  }

  _forget() {
    this._session = null;
    saveSession(null);
    this._set({ view: null, restoring: false });
  }

  _apply(name, event) {
    const view = this.state.view;
    const reduce = reducers[name];
    if (!view || !reduce || event?.game_id !== view.game_id) return;
    const next = structuredClone(view);
    reduce(next, event);
    this._set({ view: next });
  }

  async _send(name, payload) {
    const reply = await this._socket.timeout(ACK_TIMEOUT_MS).emitWithAck(name, payload);
    if (isErrorReply(reply)) throw new GameError(reply.code, reply.message, reply.request);
    return reply;
  }

  _set(changes) {
    this.state = { ...this.state, ...changes };
    for (const listener of this._listeners) listener(this.state);
  }
}

export const game = new Game();
