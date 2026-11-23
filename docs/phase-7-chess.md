# Phase 7 — Chess: move generation, search and game review

```
edge-engine play chess                         # play White against the engine (depth 3)
edge-engine play chess -o colour=black -o depth=4
edge-engine play chess -o mode=drills          # board vision and mate-in-one puzzles
edge-engine lab chess                          # perft, engine checks, review of the Opera Game
edge-engine lab chess -o pgn=mygame.pgn        # review any game
```

Type moves in SAN (`Nf3`, `exd5`, `O-O`, `e8=Q`) or UCI (`g1f3`).

---

## 1. Move generation and perft

The board is a **0x88** grid: 128 squares numbered 16 × rank + file. The real board is the 64 squares where `square & 0x88 == 0`, so "did that step leave the board?" is a single bit test. Pieces are signed numbers (White positive).

Legal moves are found in two steps:
1. generate **pseudo-legal** moves: pawn pushes and double pushes, captures, en passant, promotions to all four pieces, knight and king steps, sliding rays, and castling when the squares between are empty and the king's path is not attacked;
2. **make** each move and keep it only if the mover's king is not attacked; then **undo** it from a stack that stores the captured piece, castling rights, en passant square, clocks and hash.

**Perft** counts every legal move sequence to a fixed depth. Published counts for standard test positions make it the standard correctness test: any bug in castling, en passant, promotions or pins changes the totals. All six standard positions match:

| Position | Depth 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| Start | 20 | 400 | 8,902 | 197,281 |
| Kiwipete | 48 | 2,039 | 97,862 | 4,085,603 |
| Position 3 | 14 | 191 | 2,812 | 43,238 |
| Position 4 | 6 | 264 | 9,467 | 422,333 |
| Position 5 | 44 | 1,486 | 62,379 | 2,103,487 |
| Position 6 | 46 | 2,079 | 89,890 | 3,894,594 |

Depths 1-3 run in every test; depth 4 (about 10.5 million positions, around 23 seconds) runs in the slow tests and CI.

Each position also has a **Zobrist hash**: XOR together a fixed random 64-bit number for every (piece, square), plus numbers for the side to move, the castling rights and the en passant file. A move changes only a few terms, so the hash is updated incrementally. The tests check it against a full recomputation after every move of many random games.

---

## 2. The engine

**Negamax with alpha-beta.** Chess is zero-sum, so "my best score" is minus "your best score" one move later. Alpha-beta keeps a window [α, β] of scores that still matter and stops searching a move as soon as it proves the opponent would never allow the position. With good move ordering this searches roughly the square root of the full tree.

| Part | What it does |
|---|---|
| Iterative deepening | search depth 1, 2, 3, ...; each pass orders the next |
| Transposition table | remembers each position's depth, score, bound and best move, keyed by hash |
| Move ordering | the table move first, then captures by most valuable victim / least valuable attacker, then "killer" moves, then history scores |
| Quiescence search | at the horizon, keep searching captures, so the engine never stops in the middle of an exchange |
| Check extension | when in check at the horizon, search one more ply, so mates just past the horizon are seen |
| Mate scores | 100,000 − plies, so shorter mates are preferred |
| Draws | fifty-move rule, repetition, insufficient material |

The **evaluation** is material (100 / 320 / 330 / 500 / 900) plus piece-square tables (the "simplified evaluation function": pawns rewarded for advancing and centralising, knights for the centre, a king table that blends from "hide behind pawns" to "centralise" as pieces come off), plus 30 for the bishop pair.

It finds every built-in mate in one, a mate in two with two rooks, and wins a hanging queen. Against random moves it wins material and checkmates. In pure Python it searches about 3-4 plies in a few seconds, far weaker than Stockfish. Its judgements are labelled as its own.

---

## 3. Game review (Lichess formulas)

Each position in the game is searched once. For each move, compare the mover's chances with best play against their chances after the move actually played:

```
win%     = 50 + 50 × (2 / (1 + e^(−0.00368208 × centipawns)) − 1)
accuracy = 103.1668 × e^(−0.04354 × (win% before − win% after)) − 3.1669
```

A 10-point drop in win% gives an accuracy of about 64%, and a 20-point drop about 40%. Win% turns centipawns into something that matters: a 300-centipawn swing at +1000 changes little, but at 0 it is decisive.

**Move classes** (by win% lost, our own documented thresholds; Lichess uses 0.1 / 0.2 / 0.3 on its −1 to +1 scale, which is 5 / 10 / 15 points here):

| Class | Win% lost |
|---|---|
| Best | the engine's own choice |
| Excellent | under 2 |
| Good | 2-5 |
| Inaccuracy | 5-10 |
| Mistake | 10-15 |
| Blunder | 15 or more |

Game accuracy here is the mean of the move accuracies. Lichess's own figure blends a volatility-weighted mean with a harmonic mean, so it is a little different.

**A shallow engine and the horizon.** Reviewing Morphy's "Opera Game" (1858) shows what depth means. Without the check extension, a depth-3 search called Morphy's sacrifices blunders, because the payoff was beyond what it could see. With the extension it marks 15.Bxd7+ and 16.Qb8+ as best (it sees 16...Nxb8 17.Rd8#), and flags 14...Qe6 as Black's decisive mistake. It still undervalues the long-term sacrifice 10.Nxb5. That is the horizon effect, and why strong reviews use much deeper engines.

---

## 4. What the trainer asks

**Play.** Each of your moves is a decision: every legal move is searched (default depth 2) and converted to your win%. A move within 2 points of the best counts as right. At the end: your accuracy, class counts, your biggest drops, and the game in PGN.

**Drills** (exact answers):
- How many legal moves does a given piece have? (Pins and checks count.)
- The material balance, White minus Black.
- How many legal moves give check?
- Mate in one, from a built-in set of positions, each verified in the tests to have a mate.
