def friendly_fail_message(metrics: dict, target_time_sec: float, why: str, expected_items: int) -> str:
    """Produce a concise, kid-friendly reason for no-star outcome."""
    items = max(int(metrics.get("items") or 0), int(expected_items or 20))
    if items <= 10:
        A = 0.8
    elif items <= 20:
        A = 0.85
    else:
        A = 0.9
    need = int((A * items + 0.9999))

    ftc = metrics.get("first_try_correct")
    if ftc is None:
        ftc = round(float(metrics.get("acc", 0.0)) * items)

    if why == "accuracy_below_gate":
        if need - ftc <= 1:
            return "Just one more correct and you’ll get a star!"
        return f"Great effort — {need}/{items} correct is the goal."
    if why == "too_slow":
        m = int(target_time_sec // 60); s = int(target_time_sec % 60)
        return f"Just a bit faster — finish under {m}:{str(s).zfill(2)} to earn a star."
    return "So close — one more push and you’ll have it!"
