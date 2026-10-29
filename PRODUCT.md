# Product: Slop

## Vision

A party game where an AI turns your six-word prompt into a ridiculous script, your team performs it, and everyone else races to guess what you typed. Every round is new, so the game never runs out of content.

## Why

Party games run on a fixed deck. Once you've seen the cards, the fun fades. Slop generates fresh material every round, so the hundredth game is as surprising as the first.

## Who it's for

Groups of friends playing in the same room, usually young adults at a game night. They're happy to perform, shout guesses, and play on their phones. The game can be family-friendly or adult.

## How a game works

1. **Join.** A host creates a room and shares a short code. Players join from their phones with no accounts.
2. **Form teams.** Players split into two or more teams of up to three, either by choice or at random.
3. **Assign personalities.** Each team secretly picks an AI personality (such as noir, melodrama, or absurdist) for another team. The pick shapes the scripts that team will get.
4. **Play rounds.** On its turn, a team:
   - writes a prompt of up to six words
   - gets a script of about 90 seconds, with one character for each player, that only the team can see
   - performs it while the other teams shout guesses at the original prompt
   - picks the winning guess, or says nobody got it, and then guesses which personality wrote their script
5. **Finish.** Each team plays three rounds, with tiebreakers if needed. The game ends with final scores and AI-written awards, and the group can play again.

## Scoring

| Event | Points |
| --- | --- |
| A guessing team gets the prompt (the acting team decides if it's close enough) | +1 to the guessing team |
| Someone guesses your prompt | +1 to the acting team |
| The acting team identifies its AI personality | +1 to the acting team |

Teams that act well get guessed, so the acting team earns a point too.

## Principles

- **Fresh every time.** No two scripts should feel alike.
- **Thirty seconds to start.** A room code is all you need. The rules fit in one sentence.
- **Built for the room.** Guesses are shouted and performances are live. Phones handle the parts people can't: scripts, timers, and scores.
- **Easy to perform.** Scripts are funny, short, and readable by people who aren't actors.

## Scope

**MVP**

- Rooms, lobby, teams, and anonymous personality assignment
- Phones stay in sync, and each player's view fits their role (the acting team sees the script, everyone else sees the scoreboard)
- Script generation with a family or adult content setting
- The full round loop, scoring, tiebreakers, end-of-game awards, and play again

**Later**

- More personalities, themes, and custom personalities
- Sound, animation, and polish from playtesting
- Saving and sharing favorite scripts, and a game recap
- Spectators, and joining or leaving mid-game
- Image generation mode

**Not planned**

- Accounts, profiles, or history across sessions
- Remote play or video
- Native apps (the game is a mobile-first web app)
- AI judging of guesses (players judge)
- Monetization

## Success

- Groups finish the games they start, and come back to play again
- Scripts are funny and performable, and arrive fast enough to keep the pace (target: under 5 seconds)
- Games feel balanced: prompts and personalities are neither too easy nor too hard to guess

## Open questions

- Which personalities ship first, and how do we describe them so the picks feel strategic?
- When does the acting team find out its personality, before or after performing?
- How many tiebreakers before we call it a draw?
- What happens when a team stalls on a prompt or a script falls flat? Do we use a timeout, or let them regenerate?
- Does the host need controls such as kicking a player or restarting?
