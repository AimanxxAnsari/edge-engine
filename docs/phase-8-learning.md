# Phase 8 — Learning modes: training wheels and the Claude tutor

```
edge-engine play blackjack --wheels            # learn: see each answer before you choose
edge-engine play poker --tutor                 # ask Claude with ? at any prompt
edge-engine play chess --wheels --tutor        # both
```

---

## 1. Why two kinds of mode

Every game's scored mode follows the same rule: **predict first, then see the truth.** Seeing the answer before committing turns practice into copying (the "crutch problem"). But that makes the scored modes a poor way to learn a game you don't know yet. Phase 8 adds a deliberate exception, kept separate so it never blurs the scores:

| | Scored modes | Training wheels (`--wheels`) |
|---|---|---|
| Answer shown | after you commit | before you choose |
| Your answer | counts at once | judged first, then keep it or change it |
| Clock | where the game has one | none |
| Logged as | `<game>` | `<game>:wheels`, outside your stats and the adaptive mix |
| Tutor (`--tutor`) | hints that don't give the answer away; the answer is marked *assisted* | explains everything, including the answer |

---

## 2. Training wheels

Before each question you see:
- the answer, from the same exact truth functions the scored mode uses;
- the worked explanation and the technique tip;
- a game's extra **lesson**, such as backgammon's top three plays and the shots each leaves.

After you type an answer you see what it would score, plus the game's **judgement** of that answer. Then you press Enter to keep it, or type another to compare. Examples:
- **Coin flip:** the growth rate of your bet against Kelly's, with a warning when a big bet shrinks you despite the edge.
- **Market making:** your quote's exact expected profit per trader. For noise traders, the chance each side trades times the edge. For informed traders, averaged over every value the next item could take. Then mixed by the informed share.
- **Backgammon:** the engine's score of your play and how many shots it leaves.

Forecast questions ("will this roll be at least 9?") never show their outcome early, since it hasn't happened yet.

---

## 3. The Claude tutor

Type `?` (a hint) or `? your question` at any prompt. Claude answers in a few sentences, streamed into the terminal.

**It explains the engines' numbers; it does not compute its own.** Each request includes:
- the position as shown on screen;
- the question and its choices;
- in training wheels, the exact answer, its explanation and the lesson;
- what was recently revealed, so "why was I wrong?" works right after a reveal.

Its instructions say every number must come from that data, or be simple arithmetic on it. All the probability, EV and game-theory work stays in the from-scratch engines, and the tutor is a teaching layer on top.

**In scored modes the answer is never sent before you commit.** Claude can't reveal what it hasn't been told. It is also told to point at the method rather than work out the answer. An answer given after a hint is marked *assisted*: in the reveal, in the session summary and in the history file.

**What is sent, and to whom.** Requests go to Anthropic's API. They contain the game's public explainer from `docs/`, the screen and question, and your typed question. Nothing from `local-brain/` is read or sent.

**Settings.**
- Model: `claude-opus-5-5` by default (`--tutor-model` to change).
- Effort: low, since these are short chat answers.
- The instructions and explainer are cached, so repeat questions read them cheaply.
- The API's automatic refusal fallback is on: if the main model declines, a fallback model answers.
- The session summary shows the token use and an estimated cost.

**Setup.**
```
pip install -e ".[tutor]"
export ANTHROPIC_API_KEY=...      # or: ant auth login
```
Without the package or credentials, the games work exactly as before. If the tutor can't answer (network, credentials, rate limit), the game says so and carries on.
