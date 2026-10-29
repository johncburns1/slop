"""Event logs for tests: hand-written sequences of domain events for one game.

``full_game_events()`` uses every event type in ``slop.domain.events``. When you
add an event type, add it here too, or the replay coverage test fails.
"""

from datetime import UTC, datetime, timedelta

from slop.domain import (
    GameCompleted,
    GameCreated,
    GameEvent,
    GuessAccepted,
    GuessSubmitted,
    PersonalityAssigned,
    PersonalityGuessSubmitted,
    PlayerJoined,
    PlayerJoinedTeam,
    PlayerLeft,
    PromptSubmitted,
    RoleAssigned,
    RoundCompleted,
    RoundStarted,
    ScoresUpdated,
    ScriptGenerated,
    ScriptGenerationFailed,
    ScriptReady,
    TeamFormed,
)

GAME_ID = "game-1"
T0 = datetime(2026, 1, 1, 20, 0, tzinfo=UTC)


def at(seconds: int) -> datetime:
    return T0 + timedelta(seconds=seconds)


def created(**overrides: object) -> GameCreated:
    fields: dict[str, object] = {
        "game_id": GAME_ID,
        "event_id": "e-created",
        "timestamp": T0,
        "room_code": "ABCD",
        "content_tone": "family",
        "max_players": 12,
        "rounds_per_team": 3,
    }
    fields.update(overrides)
    return GameCreated.model_validate(fields)


def lobby_events() -> list[GameEvent]:
    """Two teams of two in the lobby."""
    events: list[GameEvent] = [created()]
    for number in range(1, 5):
        events.append(
            PlayerJoined(
                game_id=GAME_ID,
                timestamp=at(number),
                player_id=f"player-{number}",
                player_name=f"Player {number}",
                socket_id=f"socket-{number}",
            )
        )
    events += [
        TeamFormed(
            game_id=GAME_ID, timestamp=at(5), team_id="team-1", team_name="Red", color="#F00"
        ),
        TeamFormed(
            game_id=GAME_ID, timestamp=at(6), team_id="team-2", team_name="Blue", color="#00F"
        ),
    ]
    for number in range(1, 5):
        team_id = "team-1" if number <= 2 else "team-2"
        events.append(
            PlayerJoinedTeam(game_id=GAME_ID, player_id=f"player-{number}", team_id=team_id)
        )
    return events


def round_zero_events() -> list[GameEvent]:
    """Personalities assigned and team 1 has its script and roles for round 0."""
    return [
        PersonalityAssigned(
            game_id=GAME_ID, team_id="team-1", personality_id="noir", assigned_by_team_id="team-2"
        ),
        PersonalityAssigned(
            game_id=GAME_ID,
            team_id="team-2",
            personality_id="melodrama",
            assigned_by_team_id="team-1",
        ),
        RoundStarted(game_id=GAME_ID, timestamp=at(10), round_number=0, acting_team_id="team-1"),
        PromptSubmitted(
            game_id=GAME_ID, round_number=0, prompt="Cat steals the moon", submitted_by="player-1"
        ),
        ScriptGenerated(
            game_id=GAME_ID,
            timestamp=at(12),
            round_number=0,
            script_content="Night. A cat eyes the moon.",
            personality_id="noir",
            roles=[
                {"name": "Cat", "description": "A cunning cat", "lines": ["Mine."]},
                {"name": "Moon", "description": "A worried moon"},
            ],
            word_count=6,
            estimated_duration=3,
        ),
        RoleAssigned(
            game_id=GAME_ID,
            round_number=0,
            player_id="player-1",
            role_name="Cat",
            character_description="A cunning cat",
        ),
        RoleAssigned(
            game_id=GAME_ID,
            round_number=0,
            player_id="player-2",
            role_name="Moon",
            character_description="A worried moon",
        ),
    ]


def round_zero_scored_events() -> list[GameEvent]:
    """Team 2 guesses team 1's prompt, team 1 names its personality, and the round ends."""
    return [
        GuessSubmitted(
            game_id=GAME_ID, timestamp=at(20), round_number=0, team_id="team-2", guess="Cat crime"
        ),
        GuessSubmitted(
            game_id=GAME_ID, timestamp=at(21), round_number=0, team_id="team-2", guess="Moon heist"
        ),
        GuessAccepted(game_id=GAME_ID, round_number=0, team_id="team-2"),
        PersonalityGuessSubmitted(game_id=GAME_ID, round_number=0, personality_guess="noir"),
        ScoresUpdated(game_id=GAME_ID, round_number=0, score_changes={"team-1": 2, "team-2": 1}),
        RoundCompleted(game_id=GAME_ID, round_number=0, final_scores={"team-1": 2, "team-2": 1}),
    ]


def full_game_events() -> list[GameEvent]:
    """A short game that uses every event type, ending with team 1 winning."""
    return [
        *lobby_events(),
        PlayerJoined(
            game_id=GAME_ID,
            timestamp=at(7),
            player_id="player-5",
            player_name="Player 5",
            socket_id="socket-5",
        ),
        PlayerLeft(game_id=GAME_ID, player_id="player-5"),
        *round_zero_events(),
        ScriptGenerationFailed(game_id=GAME_ID, round_number=0, team_id="team-1"),
        ScriptReady(game_id=GAME_ID, round_number=0, acting_team_id="team-1"),
        *round_zero_scored_events(),
        GameCompleted(
            game_id=GAME_ID, final_scores={"team-1": 2, "team-2": 1}, winner_team_id="team-1"
        ),
    ]
