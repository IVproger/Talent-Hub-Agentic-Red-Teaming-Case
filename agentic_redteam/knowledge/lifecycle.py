"""US-36: deterministic lifecycle updates after an E8 replay."""
from __future__ import annotations

from .store import KnowledgeStore


def advance_retests(
    store: KnowledgeStore,
    source_run_ids: list[str],
    after: dict,
) -> list[dict]:
    """Advance fixed, state-proven source findings from a replay result.

    A replay is evidence only for scenarios it actually reran.  Human-owned
    statuses other than ``fixed`` are deliberately left untouched.
    """
    tested = {
        (item.get("scenario_id"), item.get("mode"))
        for item in after.get("attempts", [])
        if item.get("scenario_id") and item.get("verdict") != "error"
    }
    # Older/minimal findings fixtures may not contain the attempts table, but
    # every finding still proves that its scenario was tested.
    remaining = {
        (item.get("scenario_id"), item.get("mode"))
        for item in after.get("findings", [])
        if item.get("scenario_id") and item.get("verdict") == "proven"
    }
    tested.update(remaining)
    updates = []
    after_run = str(after.get("run_id", ""))
    for source_run_id in dict.fromkeys(source_run_ids):
        for attack in store.all_for_run(source_run_id):
            scenario_id = attack.get("scenario_id")
            key = (scenario_id, attack.get("mode"))
            if (
                attack.get("status") != "fixed"
                or attack.get("verdict") != "proven"
                or key not in tested
            ):
                continue
            note = f"Автопереход после перепроверки {after_run or 'без run_id'}."
            store.set_status(attack["id"], "retested", note)
            outcome = "reopened" if key in remaining else "closed"
            updated = store.set_status(
                attack["id"],
                outcome,
                "Атака снова доказана." if outcome == "reopened"
                else "Атака больше не доказана.",
            )
            updates.append({
                "attack_id": attack["id"],
                "scenario_id": scenario_id,
                "status": updated["status"],
                "retest_run_id": after_run,
            })
    return updates
