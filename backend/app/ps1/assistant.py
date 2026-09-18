from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from app.ps1.safety import legal_mix, possession_usage


INTENTS = {"activity_move_reason", "downstream_risk", "capacity_status", "co_share_status", "handover_brief"}
_calls = defaultdict(deque)
_lock = threading.Lock()
_gemini_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="schedule-assistant")


def enforce_query_rate(job_id, limit=20, window=60):
    now = time.monotonic()
    with _lock:
        calls = _calls[job_id]
        while calls and calls[0] <= now - window: calls.popleft()
        if len(calls) >= limit: return False
        calls.append(now); return True


def answer_question(instance, solution, question, diff=None):
    parsed, mode = _parse_with_gemini(question)
    if not parsed:
        parsed = _parse_deterministic(question); mode = "deterministic"
    intent = parsed.get("intent") if parsed else None
    entities = parsed.get("entities", {}) if parsed else {}
    if intent not in INTENTS:
        return {"answer": "I could not map that question to a supported schedule check. Try asking why an activity moved, about downstream risk, capacity, co-sharing, or a handover week.",
                "intent": "unsupported", "evidence": [], "mode": mode}
    handlers = {
        "activity_move_reason": _move_reason, "downstream_risk": _downstream,
        "capacity_status": _capacity, "co_share_status": _co_share, "handover_brief": _handover,
    }
    answer, evidence = handlers[intent](instance, solution, entities, diff)
    return {"answer": answer, "intent": intent, "evidence": evidence, "mode": mode}


def _parse_deterministic(question):
    text = question.strip(); lower = text.lower()
    aids = re.findall(r"\bA\d+\b", text, re.I)
    contracts = re.findall(r"\bC\d+\b", text, re.I)
    locations = re.findall(r"\b(?:SEC|PLAT):[A-Z0-9_:]+", text, re.I)
    weeks = [int(value) for value in re.findall(r"\bweek\s+(\d+)\b", lower)]
    entities = {"activity_ids": [a.upper() for a in aids], "contract_ids": [c.upper() for c in contracts],
                "location_id": locations[0].upper() if locations else None, "weeks": weeks}
    if "moved" in lower or ("why" in lower and aids): intent = "activity_move_reason"
    elif "downstream" in lower or "risk" in lower or "delay" in lower: intent = "downstream_risk"
    elif "capacity" in lower or "hotspot" in lower: intent = "capacity_status"
    elif "share" in lower or "co-worker" in lower or "coworker" in lower: intent = "co_share_status"
    elif "handover" in lower or "brief" in lower or ("week" in lower and not locations): intent = "handover_brief"
    else: intent = None
    return {"intent": intent, "entities": entities}


def _parse_with_gemini(question):
    project = os.getenv("GOOGLE_CLOUD_PROJECT"); location = os.getenv("GOOGLE_CLOUD_LOCATION")
    model = os.getenv("RAILFLOW_GEMINI_MODEL")
    if not all((project, location, model)): return None, "deterministic"
    def invoke():
        from google import genai
        client = genai.Client(vertexai=True, project=project, location=location)
        prompt = ("Classify the schedule question. Return JSON only with intent and entities. "
                  f"Allowed intents: {sorted(INTENTS)}. Entities keys: activity_ids, contract_ids, location_id, weeks. Question: {question}")
        response = client.models.generate_content(model=model, contents=prompt,
                                                  config={"response_mime_type": "application/json"})
        value = json.loads(response.text)
        return value if value.get("intent") in INTENTS and isinstance(value.get("entities", {}), dict) else None
    future = _gemini_pool.submit(invoke)
    try: return future.result(timeout=8), "gemini-assisted"
    except (Exception, TimeoutError):
        future.cancel(); return None, "deterministic"


def _move_reason(instance, solution, entities, diff):
    aid = next(iter(entities.get("activity_ids") or []), None)
    if not aid or not diff: return "Ask about a moved activity ID in a revised schedule.", []
    item = next((row for row in diff["activity_changes"] if row["activity_id"] == aid), None)
    if not item: return f"{aid} did not change between the baseline and revised schedules.", [aid]
    labels = {"direct_disruption": "its baseline possession intersects the disrupted location and weeks",
              "predecessor_impact": "an upstream predecessor is in the disruption impact chain",
              "optimizer_rebalance": "the optimiser rebalanced unaffected future work while preserving the best policy score"}
    before = ", ".join(f'W{x["week"]}' for x in item["before"]); after = ", ".join(f'W{x["week"]}' for x in item["after"])
    return f"{aid} moved from {before} to {after} because {labels[item['reason']] }.", [aid, item["contract_number"]]


def _downstream(instance, solution, entities, diff):
    seeds = set(entities.get("activity_ids") or [])
    contracts = set(entities.get("contract_ids") or [])
    if contracts: seeds |= {aid for aid, a in instance.activities.items() if a.contract_number in contracts}
    if not seeds and diff: seeds = set(diff.get("directly_affected_activities", []))
    descendants = set(); frontier = set(seeds)
    while frontier:
        parent = frontier.pop()
        for aid, activity in instance.activities.items():
            if activity.predecessor_activity_id == parent and aid not in descendants:
                descendants.add(aid); frontier.add(aid)
    late = {r.contract_number: r.overrun_days for r in solution.results if r.overrun_days}
    impacted = sorted({instance.activities[a].contract_number for a in descendants if a in instance.activities})
    return (f"{len(descendants)} downstream activities are linked to the selected work. "
            f"Impacted contracts: {', '.join(impacted) or 'none'}; currently late: "
            f"{', '.join(f'{c} ({d} days)' for c, d in late.items()) or 'none'}.", sorted(seeds | descendants))


def _capacity(instance, solution, entities, diff):
    location = entities.get("location_id"); weeks = entities.get("weeks") or []
    if not location or not weeks: return "Include a location ID and week, for example: capacity at SEC:ALP:S01_S02:EB week 8.", []
    week = weeks[0]
    item = next((u for u in possession_usage(instance, solution.accesses, solution.occupancy)
                 if u["location_id"] == location and u["week"] == week), None)
    used = item["work_possessions"] if item else 0
    nominal = instance.supply.get(location)
    if not nominal: return f"{location} is not a known supply location.", [location]
    return f"{location} uses {used} of {nominal.supply_capacity} nominal slots in week {week}.", [location, f"week:{week}"]


def _co_share(instance, solution, entities, diff):
    aids = entities.get("activity_ids") or []
    if not aids: return "Include an activity ID to inspect its co-sharing assignments.", []
    aid = aids[0]
    groups = defaultdict(set)
    for row in solution.occupancy: groups[row.location_id, row.week, row.co_share_group].add(row.activity_id)
    peers = sorted({peer for members in groups.values() if aid in members for peer in members if peer != aid})
    if len(aids) > 1:
        other = aids[1]; actual = other in peers
        compatible = aid in instance.activities and other in instance.activities and legal_mix(instance, [aid, other])
        return f"{aid} and {other} {'do' if actual else 'do not'} currently co-share. Their access types are {'compatible' if compatible else 'not compatible'}.", aids[:2]
    return f"{aid} co-shares with {', '.join(peers) if peers else 'no other activities'}.", [aid, *peers]


def _handover(instance, solution, entities, diff):
    weeks = entities.get("weeks") or []
    if not weeks: return "Include a week for the handover brief.", []
    start, end = min(weeks), max(weeks)
    rows = [r for r in solution.accesses if start <= r.week <= end]
    activities = sorted({r.activity_id for r in rows}); eclo = sum(r.eclo for r in rows)
    contracts = sorted({instance.activities[a].contract_number for a in activities})
    return (f"Weeks {start}-{end}: {len(rows)} access occurrences across {len(activities)} activities and "
            f"{len(contracts)} contracts, with {eclo} ECLO nights. Contracts: {', '.join(contracts) or 'none'}.",
            [*activities, *(f"week:{w}" for w in range(start, end + 1))])
