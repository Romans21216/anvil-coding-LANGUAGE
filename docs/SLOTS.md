# ANVIL SLOTS

A complete 2D slot machine written in Anvil, drawn entirely from primitives —
no image files, no external assets. Every symbol, panel, button and bulb is a
rectangle, circle or line drawn by the engine's 2D path.

Run it from Windows:

```
python compiler/anvil.py examples/slots.ANVL -o slots.exe
slots.exe
```

## What it does

- **3 reels × 3 rows**, one payline across the middle row.
- **Seven symbols**, each drawn procedurally: cherry (two circles and stems),
  lemon, bell, triple BAR, diamond outline, seven, and a wild chip.
- **Weighted reels**: cherry 30%, lemon 24%, bell 16%, bar 12%, diamond 10%,
  seven 6%, wild 2% — so the jackpot is rare without being impossible.
- **Payouts** on the payline: three of a kind pays ×5 (cherry) up to ×250 (wild),
  two BAR or better pays ×2, and wild substitutes for any symbol.
- **Animation**: each reel spins and stops in turn (0.9 s, 1.18 s, 1.46 s),
  then the result settles at 1.75 s.
- **A paytable overlay** (P) with the symbol payouts and odds, and click-to-close.
- **Classic cabinet**: bulbs along the top and bottom that pulse, a gold payline
  that flashes on a win, credits / bet / win readouts.

## Controls

| input | effect |
|---|---|
| SPACE or click SPIN | spin once (costs the current bet) |
| ← / → or the − / + buttons | bet 1 through 20 |
| P | paytable open/close |
| R | reset credits to 200 |
| click anywhere while the paytable is open | close it |

## How the state machine works

`fn(spin_start)` takes the bet, fills `grid` with nine freshly weighted symbols
and sets `state = 1`. `fn(update)` advances `spin_t`; each reel shows scrolling
symbols until its own stop time, then snaps to its column of `grid`. At 1.75 s
`fn(settle)` resolves the middle row, substitutes wilds, adds the payout to
credits and sets `state = 2`. `fn(draw)` renders the current state — so the
display never owns any game logic.

The reels are decided **before** they animate, which is what lets the animation
stop on a predetermined result instead of a result derived from where the
graphics happened to land.

## Verified by running it

- click SPIN → credits 200 → 195, reels land on a mixed spread
- click `+` twice → bet 5 → 7, next spin costs 7 (credits 200 → 193)
- a forced-jackpot build (every reel a seven) → WIN 500, PAYOUT 500,
  credits 695, payline flashing
- P → paytable over a dimmed screen; click → closes
- both backends are not a factor here: the scene engine is the C/MSVC path,
  which is the only one that renders windows
