from typing import Optional, Tuple
from itertools import product

def _oldest_star_life_rounds(stars_recent: str) -> int:
    s = (stars_recent or "")[-5:]
    if "1" not in s:
        return 0
    L = len(s)
    idx = s.find("1")  # oldest star index
    return (5 - L) + idx

def need_hint_text(stars_recent: str, this_star: bool) -> str:
    s0 = (stars_recent or "")[-5:]
    s = (s0 + ("1" if this_star else "0"))[-5:]
    c = s.count("1")

    if c == 0:
        return "Need 3 stars in the next 5 rounds to level up"

    life = _oldest_star_life_rounds(s)
    if c == 1 and life >= 2:
        return f"Need 2 stars in the next {life} rounds to level up"
    if c == 2 and life >= 1:
        return f"Need 1 star in the next {life} rounds to level up"

    best: Optional[Tuple[int,int]] = None
    for horizon in range(1, 6):
        for seq in product([0,1], repeat=horizon):
            k = sum(seq)
            win = s
            ok = False
            for b in seq:
                win = (win + ("1" if b else "0"))[-5:]
                if win.count("1") >= 3 and win[-3:].count("1") >= 2:
                    ok = True
                    break
            if ok and (best is None or (k, horizon) < best):
                best = (k, horizon)
        if best:
            k, h = best
            if k == 1 and h == 1:
                return "Need a star next round to level up"
            return f"Need {k} of the next {h} rounds to level up"
    return "Get 3 of your last 5 stars to level up"
