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

The board is a **0x88** grid: 128 squares numbered

```math
\text{square} = 16 \cdot \text{rank} + \text{file}, \qquad 0 \le \text{rank}, \text{file} \le 7 .
```

The real board is the 64 squares where $`\text{square} \ \&\  \mathtt{0x88} = 0`$: bit 3 is set for files 8-15 and bit 7 for ranks past the board, so "did that step leave the board?" is a single bit test. A knight on h1 (square 7) stepping $`+18`$ lands on 25, which has bit 3 set: off the board. Pieces are signed numbers (White positive).

Legal moves are found in two steps:
1. generate **pseudo-legal** moves: pawn pushes and double pushes, captures, en passant, promotions to all four pieces, knight and king steps, sliding rays, and castling when the squares between are empty and the king's path is not attacked;
2. **make** each move and keep it only if the mover's king is not attacked; then **undo** it from a stack that stores the captured piece, castling rights, en passant square, clocks and hash.

**Perft** counts every legal move sequence to a fixed depth:

```math
\mathrm{perft}(s, 0) = 1, \qquad \mathrm{perft}(s, d) = \sum_{m \in \mathrm{legal}(s)} \mathrm{perft}(s \cdot m,\ d - 1) .
```

Published counts for standard test positions make it the standard correctness test: any bug in castling, en passant, promotions or pins changes the totals. All six standard positions match:

| Position | Depth 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| Start | 20 | 400 | 8,902 | 197,281 |
| Kiwipete | 48 | 2,039 | 97,862 | 4,085,603 |
| Position 3 | 14 | 191 | 2,812 | 43,238 |
| Position 4 | 6 | 264 | 9,467 | 422,333 |
| Position 5 | 44 | 1,486 | 62,379 | 2,103,487 |
| Position 6 | 46 | 2,079 | 89,890 | 3,894,594 |

Depths 1-3 run in every test; depth 4 (about 10.5 million positions, around 23 seconds) runs in the slow tests and CI.

Each position also has a **Zobrist hash**: with a fixed random 64-bit number $`z`$ for every (piece, square) pair, the side to move, each castling state and each en passant file,

```math
H(s) = \bigoplus_{(p,\,q) \in s} z_{p,q} \ \oplus\ z_{\text{side}} \ \oplus\ z_{\text{castling}} \ \oplus\ z_{\text{ep}} .
```

XOR is its own inverse, so a move from $`q_1`$ to $`q_2`$ updates it in a few steps, $`H \leftarrow H \oplus z_{p,q_1} \oplus z_{p,q_2} \oplus \dots`$ (plus any captured piece and changed rights). Two different positions share a hash with probability about $`2^{-64}`$. The tests check the incremental hash against a full recomputation after every move of many random games.

---

## 2. The engine

**Negamax with alpha-beta.** Chess is zero-sum, so "my best score" is minus "your best score" one move later:

```math
v(s) = \max_{m \in \mathrm{legal}(s)} \bigl(-v(s \cdot m)\bigr) .
```

Alpha-beta passes a window $`(\alpha, \beta)`$: $`\alpha`$ is the score the side to move is already guaranteed, $`\beta`$ the most the opponent will allow. As soon as a move scores $`\ge \beta`$ the opponent would avoid this position, so the remaining moves are skipped (a cutoff). With branching factor $`b`$ and depth $`d`$, perfect move ordering cuts the number of positions from $`b^d`$ to about

```math
b^{\lceil d/2 \rceil} + b^{\lfloor d/2 \rfloor} - 1,
```

roughly the square root of the full tree, which doubles the depth reachable. From the start position, depth 4 takes about 2,800 nodes against 197,281 for full perft.

| Part | What it does |
|---|---|
| Iterative deepening | search depth 1, 2, 3, ...; each pass orders the next |
| Transposition table | remembers each position's depth, score, bound and best move, keyed by hash |
| Move ordering | the table move first, then captures by most valuable victim / least valuable attacker, then "killer" moves, then history scores |
| Quiescence search | at the horizon, keep searching captures, so the engine never stops in the middle of an exchange |
| Check extension | when in check at the horizon, search one more ply, so mates just past the horizon are seen |
| Mate scores | $`100\,000 - \text{plies}`$, so shorter mates are preferred |
| Draws | fifty-move rule, repetition, insufficient material |

The **evaluation**, in centipawns from White's side (and negated for Black to move), is

```math
E = \sum_{\text{pieces}} \pm\bigl(v_{\text{piece}} + \mathrm{PST}_{\text{piece}}(\text{square})\bigr) \ \pm\ \bigl(\lambda\, K_{\text{mid}} + (1 - \lambda)\, K_{\text{end}}\bigr) \ \pm\ 30\,[\text{bishop pair}],
```

with material $`v`$ = 100 / 320 / 330 / 500 / 900 for pawn, knight, bishop, rook and queen, and piece-square tables (the "simplified evaluation function": pawns rewarded for advancing and centralising, knights for the centre). The king's table blends from "hide behind pawns" to "centralise" as pieces come off, with

```math
\lambda = \min\left(1,\ \frac{\text{non-pawn material on the board}}{6200}\right) .
```

It finds every built-in mate in one, a mate in two with two rooks, and wins a hanging queen. Against random moves it wins material and checkmates. In pure Python it searches about 3-4 plies in a few seconds, far weaker than Stockfish. Its judgements are labelled as its own.

---

## 3. Game review (Lichess formulas)

Each position in the game is searched once, giving a score $`e_i`$ for the side to move in position $`i`$. For move $`i`$ (from position $`i`$ to $`i + 1`$), the mover's chances with best play and after the move actually played are

```math
W_{\text{before}} = W(e_i), \qquad W_{\text{after}} = W(-e_{i+1}),
```

using Lichess's published formulas, with mates counted as $`\pm 10\,000`$ centipawns:

```math
W(c) = 50 + 50\left(\frac{2}{1 + e^{-0.00368208\,c}} - 1\right),
\qquad
\text{accuracy} = 103.1668\, e^{-0.04354\,\Delta} - 3.1669, \quad \Delta = \max\bigl(0,\ W_{\text{before}} - W_{\text{after}}\bigr) .
```

$`W(0) = 50`$ and $`W(c) + W(-c) = 100`$. A 10-point drop in win% gives an accuracy of about 63.6%, and a 20-point drop about 40.0%. The logistic curve flattens at the ends, so win% turns centipawns into something that matters: a 300-centipawn swing at +1000 changes little, but at 0 it is decisive.

**Move classes** (by win% lost, our own documented thresholds; Lichess uses 0.1 / 0.2 / 0.3 on its −1 to +1 scale, which is 5 / 10 / 15 points here):

| Class | Win% lost |
|---|---|
| Best | the engine's own choice |
| Excellent | under 2 |
| Good | 2-5 |
| Inaccuracy | 5-10 |
| Mistake | 10-15 |
| Blunder | 15 or more |

Game accuracy here is the mean of the move accuracies, $`\tfrac{1}{N} \sum_i \text{accuracy}_i`$ over one side's $`N`$ moves. Lichess's own figure blends a volatility-weighted mean with a harmonic mean, so it is a little different.

**A shallow engine and the horizon.** Reviewing Morphy's "Opera Game" (1858) shows what depth means. Without the check extension, a depth-3 search called Morphy's sacrifices blunders, because the payoff was beyond what it could see. With the extension it marks 15.Bxd7+ and 16.Qb8+ as best (it sees 16...Nxb8 17.Rd8#), and flags 14...Qe6 as Black's decisive mistake. It still undervalues the long-term sacrifice 10.Nxb5. That is the horizon effect, and why strong reviews use much deeper engines.

---

## 4. What the trainer asks

**Play.** Each of your moves is a decision: every legal move $`m`$ is searched (default depth 2) and converted to your win%, $`W(-e(s \cdot m))`$. A move within 2 points of the best counts as right. At the end: your accuracy, class counts, your biggest drops, and the game in PGN.

**Drills** (exact answers):
- How many legal moves does a given piece have? (Pins and checks count.)
- The material balance, White minus Black.
- How many legal moves give check?
- Mate in one, from a built-in set of positions, each verified in the tests to have a mate.
