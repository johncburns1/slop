"""Named end-to-end scenarios, played by the simulated players in ``tests.sim``.

A ``Scenario`` (in ``scenario``) is a name, the game setup, each bot's script,
and the outcome expected. ``library`` holds the scenarios; ``test_library``
plays every one of them and writes its evidence for the validation report.
To add a scenario, define it in ``library`` and add it to ``SCENARIOS``.

``recovery`` holds the scenarios that need something to go wrong partway
through (a dropped connection, a server crash); ``test_recovery`` plays them.
"""
