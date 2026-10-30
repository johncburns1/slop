"""A whole game played by scripted bots, checked against what each player saw."""

from slop.domain.events import GameCompleted, PromptSubmitted, RoleAssigned, ScriptGenerated
from tests.evidence import write_evidence
from tests.sim.bot import CORRECT, BotScript
from tests.sim.client import InProcessServer
from tests.sim.table import Table

# Two teams of two, two rounds each. Rounds are numbered from 0, as in the game:
# Red acts in rounds 0 and 2, Blue in rounds 1 and 3.
SCRIPTS = (
    BotScript(
        name="Alice",
        team="Red",
        pick="melodrama",
        prompts={0: "Penguins open a tiny bakery", 2: "Wizard loses his only hat"},
        personality_guesses={0: "noir", 2: "noir"},  # both right: +1, +1
    ),
    BotScript(name="Bob", team="Red", guesses={1: CORRECT}),  # Red +1, Blue +1
    BotScript(
        name="Carol",
        team="Blue",
        pick="noir",
        prompts={1: "Robots argue about breakfast cereal", 3: "Grandma wins the space race"},
        guesses={2: CORRECT},  # Blue +1, Red +1
        personality_guesses={1: "absurdist", 3: "melodrama"},  # wrong, then right: +1
    ),
    BotScript(name="Dave", team="Blue", guesses={0: "Birds bake bread", 2: "Hat trick"}),
)


async def test_a_scripted_game_runs_from_lobby_to_final_scores():
    server = InProcessServer.with_stand_ins()
    room_code = await server.create_game(rounds_per_team=2)
    table = await Table.seat(server, room_code, SCRIPTS)

    completed = await table.play()

    red, blue = (table.team_id_named(name) for name in ("Red", "Blue"))
    assert completed.final_scores == {red: 4, blue: 3}
    assert completed.winner_team_id == red
    for bot in table.bots:
        assert [e for e in bot.inbox() if isinstance(e, GameCompleted)] == [completed]

    write_evidence("simulated-game/player-views.md", table.views_markdown())


async def test_only_the_acting_team_ever_receives_the_prompt_script_and_roles():
    server = InProcessServer.with_stand_ins()
    room_code = await server.create_game(rounds_per_team=2)
    table = await Table.seat(server, room_code, SCRIPTS)
    await table.play()

    secret = (PromptSubmitted, ScriptGenerated, RoleAssigned)
    for bot in table.bots:
        acted_in = {n for n, team_id in bot.view().acting_teams.items() if team_id == bot.team_id}
        received_in = [e.round_number for e in bot.inbox() if isinstance(e, ScriptGenerated)]
        assert sorted(received_in) == sorted(acted_in), bot.name
        for event in bot.inbox():
            if isinstance(event, secret):
                assert event.round_number in acted_in, (bot.name, event)
    assert server.realtime.who_received(ScriptGenerated) == {
        bot.socket_id for bot in table.bots
    }  # everyone acted at some point, each only in their own rounds


async def test_bots_with_default_scripts_play_a_game_to_the_end():
    server = InProcessServer.with_stand_ins()
    room_code = await server.create_game(rounds_per_team=1)
    table = await Table.seat(
        server,
        room_code,
        [BotScript(name=n, team=t) for n, t in (("A", "X"), ("B", "Y"), ("C", "X"), ("D", "Y"))],
    )

    completed = await table.play()

    # By default nobody guesses the prompt, every team picks noir for the next,
    # and every acting team guesses noir. So each round scores 1 for the acting
    # team, the teams stay level through both tiebreaker cycles, and it's a draw.
    x, y = table.team_id_named("X"), table.team_id_named("Y")
    assert completed.final_scores == {x: 3, y: 3}
    assert completed.winner_team_id is None
    assert sorted(table.bots[0].view().acting_teams) == list(range(6))
