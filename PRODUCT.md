# Product Definition: AI Party Game

## 1. Product Vision

A dynamic, AI-powered party game that turns simple prompts into hilarious acting challenges, creating unique and memorable moments every time you play - all from your phone.

## 2. Problem Statement

**What:** Existing party games rely on static, pre-canned content that becomes predictable and stale after repeated plays.

**Who:** Friend groups, party hosts, and social gatherings looking for fresh, engaging entertainment.

**Why:** People want party games that are replayable, unpredictable, and generate unique experiences each time. Current games can't adapt or create new content - once you've played through the deck, the magic fades.

## 3. Target Users

**Primary Users:**

- Young adults (20s-30s) hosting game nights
- Friend groups looking for in-person social activities
- Party hosts wanting easy-to-setup entertainment

**Secondary Users:**

- Families looking for dynamic game experiences
- Social groups at gatherings, events, or parties

**User Characteristics:**

- Comfortable with technology (web apps on phones)
- Enjoy improv, charades, or creative party games
- Want low-setup, high-fun activities
- Playing in-person (yelling guesses, performing together)
- May prefer adult humor or family-friendly content (configurable)

## 4. Product Goals

1. **Create Unique Experiences:** Every script generated should feel fresh and unpredictable
2. **Maximize Replayability:** Game should remain fun across multiple sessions without feeling repetitive
3. **Low Barrier to Entry:** Room code to join, no accounts, easy to explain rules
4. **Become Go-To Party Game:** Be the game friends reach for at social gatherings
5. **Scalable Fun:** Work well with 2-6+ teams of varying sizes
6. **Strategic Depth:** AI personality selection adds another layer of gameplay and competition
7. **Seamless Multi-Device:** Everyone on their phones, synchronized game state, intuitive UX

## 5. Core Features

### Must Have (MVP)

#### Game Setup & Joining

- [ ] Create game flow
  - [ ] Generate unique room code
  - [ ] Configure content tone (family-friendly vs adult)
- [ ] Join game flow
  - [ ] Enter room code to join
  - [ ] See lobby with current players
- [ ] Team formation
  - [ ] Add teams (2+ teams)
  - [ ] Players pick their team (max 3 per team)
  - [ ] Option for random shuffle of players to teams
  - [ ] Visual confirmation of team rosters
- [ ] Anonymous AI personality assignment
  - [ ] Each team picks a personality for another team
  - [ ] Assignment is anonymous (teams don't know who picked for them)
  - [ ] Confirmation when all personalities assigned

#### Multi-Device Experience

- [ ] Real-time synchronization across all players' devices
- [ ] Dynamic view based on game state and player's team
- [ ] **Default view (when not acting):**
  - [ ] Current scores for all teams
  - [ ] Which team is currently acting
  - [ ] Current round number
  - [ ] Game metadata (rounds remaining, etc.)
- [ ] **Acting team view (when it's your turn):**
  - [ ] Prompt entry text area (6 word max)
  - [ ] First team member to submit sets the prompt
  - [ ] After generation: Script displayed with assigned role
  - [ ] Role assignment includes character name and characteristics
  - [ ] Original prompt shown at top of script as reminder

#### AI Script Generation

- [ ] Generate scripts based on 6-word prompts
- [ ] Scripts should be MAX 90 seconds of spoken content
- [ ] Generate exactly as many roles as team has players
- [ ] Assign roles randomly to team members
- [ ] Include character name and characteristics for each role
- [ ] Tone/style based on team's assigned AI personality
- [ ] Zany and outlandish output

#### Turn-Based Gameplay Flow

- [ ] Clear indication of whose turn it is
- [ ] Prompt entry (first team member to submit wins, but teams coordinate)
- [ ] Script generation and display to acting team only
- [ ] Performance phase (guessing teams can't see script)
- [ ] Guessing phase (1-minute timer)
  - [ ] Guessing teams yell answers in person
  - [ ] Acting team submits who won via button
  - [ ] Option to mark "nobody won"
- [ ] Personality guessing phase
  - [ ] Acting team guesses which AI personality generated their script
  - [ ] Submit guess via interface

#### Scoring System

- [ ] **Points for guessing teams:**
  - [ ] 1 point for correctly guessing the original prompt
  - [ ] Acting team decides if guess is "close enough"
- [ ] **Points for acting team:**
  - [ ] 1 point when another team guesses their prompt correctly (incentive to act well!)
  - [ ] 1 bonus point for correctly guessing their AI personality
- [ ] Score submission interface after each round
- [ ] Real-time score updates across all devices
- [ ] Persistent score display

#### Round Management

- [ ] 3 rounds per team
- [ ] Tie breaker rounds (if teams tied after all rounds)
- [ ] Clear indication of game progress

#### End Game

- [ ] Display final scores
- [ ] AI-generated fun awards (best actor, funniest script, etc.)
- [ ] Option to play again

### Should Have

- [ ] Multiple AI personality options (5-8 distinct personalities)
  - [ ] Range from subtle to completely bonkers
  - [ ] Different themes (dramatic, comedic, noir, absurdist, etc.)
  - [ ] Clear descriptions for strategic selection
- [ ] Script categories/themes (action, romance, horror, etc.)
- [ ] Game history/summary
- [ ] Visual indicators showing which team is guessing
- [ ] Sound effects for timers/transitions
- [ ] Animations for score changes
- [ ] Lobby chat while waiting for game to start

### Nice to Have

- [ ] Image generation mode (in addition to text scripts)
- [ ] Save/share particularly funny scripts
- [ ] Replay previous scripts from the session
- [ ] Custom AI personality prompts
- [ ] Background music/ambient sounds
- [ ] Score history visualization
- [ ] Game statistics (fastest guess, most points in a round, etc.)
- [ ] Spectator mode (join to watch without playing)
- [ ] Mid-game player joining/leaving handling

## 6. User Stories

### Game Setup

- As a party host, I want to create a game and share a simple room code so friends can join easily
- As a player, I want to join a game with just a room code so I can start playing quickly
- As a team, I want to pick our opponents' AI personalities anonymously so we can add challenge or chaos strategically
- As a player, I want the option to randomly shuffle into teams so we can mix things up

### Playing a Round - Acting Team

- As an acting team member, I want to enter our 6-word prompt so we can get our script
- As an acting team member, I want to see my assigned role with character details so I know who I'm playing
- As an actor, I want to view the script on my phone while performing so I don't have to memorize it
- As an acting team, I want to see the original prompt at the top of the script so we remember what we submitted
- As an acting team, I want to submit which team guessed correctly so we can award points fairly
- As an acting team, I want to earn points when we're guessed correctly so I'm motivated to perform well

### Playing a Round - Guessing Teams

- As a guessing team, I want to see clearly that another team is acting so I know to pay attention
- As a guessing team, I want to yell out guesses and compete with other teams so the game feels energetic
- As a guessing team, I want a fair timer so everyone has equal chance to guess

### Scoring & Progression

- As a player, I want to see live scores on my phone so I know the standings without asking
- As a competitive player, I want tie-breakers when scores are even so we have a clear winner
- As a player, I want to guess the AI personality for bonus points so there's an extra challenge

### End Game

- As a participant, I want fun AI-generated awards so we can celebrate the best moments
- As a group, I want the option to play again without recreating everything so we can do multiple sessions

### Replayability

- As a returning player, I want completely different scripts each time so the game stays fresh
- As a group, I want variety in script tones and styles so each round feels unique

## 7. Success Metrics

### Engagement Metrics

- Game completion rate (% of games that finish all rounds)
- Average rounds played per session
- Repeat play rate (same players coming back)
- Average time per round (is pacing good?)

### Quality Metrics

- Script generation success rate (coherent, performable scripts)
- Average script generation time (< 5 seconds ideal)
- User satisfaction (qualitative feedback from playtesting)
- Script length accuracy (actually ~1 minute when read aloud)
- Role assignment satisfaction (are roles balanced?)

### Gameplay Metrics

- AI personality guess accuracy (is it too easy/hard?)
- Acting team point earn rate (are they incentivized properly?)
- Score distribution (is the game balanced?)
- Guess success rate (are prompts too easy/hard to guess?)

### Technical Metrics

- Device synchronization accuracy (are all devices in sync?)
- Connection stability (how many disconnects?)
- Average latency for real-time updates

### Growth Metrics

- Number of unique game sessions
- Word-of-mouth referrals (friends recommending to friends)
- Becoming the "go-to" game (measured by repeat sessions)

## 8. Out of Scope

**Explicitly NOT Building (for MVP):**

- User accounts or authentication
- Remote play features (video chat, screen sharing) - assumes in-person play
- Integrated voting systems for end-game awards (AI just suggests, group decides verbally)
- Mobile native apps (web-only for MVP)
- Video recording of performances
- Leaderboards across different game sessions
- Social sharing integrations
- Payment or monetization features
- AI-powered judging or automated scoring
- Voice-to-text for guessing (guessing happens verbally, acting team marks winner)
- Game history persistence across sessions (only current session)
- Player profiles or avatars

## 9. Technical Considerations

### Architecture

- **Platform:** Progressive Web App (mobile-first, responsive design)
- **Multi-device:** Real-time synchronization required across all players' devices
- **Session Management:** Room-based game sessions with unique codes
- **State Management:** Distributed game state with authoritative server
- **In-person assumption:** Guessing happens verbally, no video/audio streaming needed

### Constraints

- **LLM API costs:** Each script generation incurs API costs; need to optimize prompt efficiency
- **Response time:** Script generation should be < 5 seconds to maintain game flow
- **Real-time sync:** All devices must stay synchronized (<1 second latency ideal)
- **Script quality:** Need effective prompting to ensure scripts are:
  - Performable by non-actors
  - Appropriate length (MAX 1 minute spoken content, ~150 words)
  - Actually zany/outlandish
  - Include exactly the right number of roles (matching team size)
  - Match the chosen AI personality
  - Include character names and characteristics for each role
- **Connection reliability:** Handle temporary disconnections gracefully
- **Mobile UX:** Must work well on various phone screen sizes

### Dependencies

- **LLM API:** OpenAI, Anthropic, or similar (for script generation)
- **Real-time backend:** WebSocket server (Socket.io, Pusher, or similar)
- **Web hosting:** Cloud platform with WebSocket support
- **Frontend framework:** React, Vue, Svelte, or similar (with mobile-first design)

### Security & Safety

- Content filtering to prevent extremely inappropriate outputs
- Rate limiting to prevent API abuse
- Room code validation and expiration
- Input validation on prompts (6 word max)
- Configurable content tone (family vs adult)
- Privacy: Only acting team sees their script

### Technical Architecture

```text
┌─────────────┐
│   Client    │ (Player's phone - React/Vue/Svelte PWA)
│  (Browser)  │
└──────┬──────┘
       │ WebSocket
       │
┌──────▼──────┐
│   Server    │ (Node.js + Socket.io / similar)
│  (Backend)  │ - Room management
│             │ - Game state synchronization
└──────┬──────┘ - Score tracking
       │
       │ HTTP/REST
       │
┌──────▼──────┐
│  LLM API    │ (OpenAI / Anthropic)
│             │ - Script generation
└─────────────┘ - Personality-based prompts
```

## 10. Open Questions

### Game Mechanics

- [ ] Which LLM provider to use? (OpenAI GPT-4, Claude, other?)
- [ ] How many AI personalities to offer initially? (suggest 5-8)
- [ ] What should the AI personalities be? (Dramatic, Absurdist, Noir, Romantic, Horror, Sci-Fi, etc.)
- [ ] How to describe AI personalities so teams can pick strategically?
- [ ] Should the acting team know which personality was chosen before or after they act?
- [ ] How many tie-breaker rounds before declaring a tie? (suggest 1-2)
- [ ] Should there be a maximum game length to prevent endless ties?
- [ ] What happens if acting team guesses personality wrong? (just don't get bonus point - confirm)
- [ ] Should personality guessing happen before or after prompt guessing? (suggest after)

### Technical

- [ ] How to handle inappropriate content generation? (content filters, reporting, manual review?)
- [ ] What's the estimated cost per game session? (based on LLM usage)
- [ ] Should we log/store generated scripts for quality improvement? (privacy considerations)
- [ ] How to handle disconnections mid-game? (reconnection grace period, game pause?)
- [ ] How long should room codes remain valid? (24 hours? Until game ends?)
- [ ] How to ensure scripts are exactly the right length? (~150 words for 1 minute)
- [ ] Should we cache/deduplicate similar prompts to save costs?

### UX/UI

- [ ] What happens if team doesn't submit a prompt (timeout)?
- [ ] Should there be a way to skip/regenerate a script if it's broken?
- [ ] How to handle edge cases (teams refusing to act, disputes on "close enough")?
- [ ] Should there be in-game help/rules reference?
- [ ] How to onboard new players who've never played before?
- [ ] Should room creator have special admin powers (kick players, restart game)?

### Content & Safety

- [ ] Do we need content warnings or age gates?
- [ ] How to ensure scripts are actually performable (not too abstract or nonsensical)?
- [ ] Should there be a report/flag feature for inappropriate outputs?

## 11. Data Models

### Game Session

```javascript
{
  id: string,
  roomCode: string, // 4-6 character code
  createdAt: timestamp,
  status: 'lobby' | 'personality_selection' | 'playing' | 'finished',
  contentTone: 'family' | 'adult',
  teams: Team[],
  players: Player[],
  rounds: Round[],
  currentRound: number,
  settings: {
    roundsPerTeam: number, // default 3
    guessTimerSeconds: number, // default 60
    maxPlayersPerTeam: number // default 3
  }
}
```

### Player

```javascript
{
  id: string,
  name: string,
  teamId: string | null,
  socketId: string, // for real-time connection
  isCreator: boolean,
  joinedAt: timestamp
}
```

### Team

```javascript
{
  id: string,
  name: string,
  color: string, // for UI differentiation
  playerIds: string[], // max 3
  score: number,
  assignedPersonality: string | null, // AI personality chosen by another team
  personalityAssignedBy: string | null // team id (kept server-side, not revealed)
}
```

### Round

```javascript
{
  id: string,
  roundNumber: number,
  actingTeamId: string,
  prompt: string, // 6 words max
  submittedBy: string, // player id who submitted first
  script: Script,
  roleAssignments: {
    [playerId: string]: {
      roleName: string,
      characterDescription: string
    }
  },
  promptGuesses: Guess[],
  promptWinnerTeamId: string | null,
  personalityGuess: string | null, // acting team's guess
  personalityCorrect: boolean,
  roundScore: {
    [teamId: string]: number // points earned this round
  },
  timestamp: timestamp
}
```

### Script

```javascript
{
  content: string, // full script text
  roles: Role[], // exactly matches acting team size
  personality: string, // which AI personality generated this
  estimatedDuration: number, // in seconds (target: ~60)
  wordCount: number,
  generatedAt: timestamp
}
```

### Role

```javascript
{
  name: string, // character name
  description: string, // character traits, motivations, quirks
  lines: string[] // optional: pre-split dialogue
}
```

### Guess

```javascript
{
  teamId: string,
  guess: string,
  timestamp: number,
  accepted: boolean // did acting team accept it?
}
```

### AI Personality

```javascript
{
  id: string,
  name: string, // e.g., "Dramatic Director", "Absurdist Theater"
  description: string, // what to expect from this personality
  systemPrompt: string, // how to instruct the LLM
  exampleScript: string // optional: show players what to expect
}
```

## 12. Timeline & Milestones

### Phase 1: MVP (Core Gameplay)

- Multi-device real-time infrastructure
  - Room creation and joining with codes
  - WebSocket synchronization across devices
  - Player and team management
- Game setup flow
  - Team formation
  - Anonymous AI personality assignment
- Core gameplay implementation
  - Prompt entry (race condition handling)
  - AI script generation with personality variants
  - Role assignment to specific players
  - Turn-based flow with proper view switching
- Scoring system
  - Dual scoring (guessing teams + acting team)
  - Personality guessing bonus
  - Score submission interface
  - Real-time score updates
- Round management (3 rounds per team)
- Tie breakers
- End game summary with AI-generated awards

### Phase 2: Enhanced Experience

- Expanded AI personality options (8-10 personalities)
- Content tone configuration (family vs adult)
- Script categories/themes
- Improved mobile UI/UX based on playtesting
- Better visual indicators for game state
- Animations and transitions
- Sound effects and feedback
- Connection resilience (handle disconnects)

### Phase 3: Extended Features

- Image generation mode
- Script saving/sharing
- Game history and statistics
- Advanced customization options
- Performance optimizations
- Cost optimization for LLM usage
- Spectator mode
- Custom personality creation

---

**Last Updated:** 2025-12-23
**Status:** Draft - Ready for Development
**Owner:** Game Development Team
