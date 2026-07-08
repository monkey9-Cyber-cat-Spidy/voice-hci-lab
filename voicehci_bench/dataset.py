"""Synthetic dataset of realistic spoken prompts with disfluencies.

Generated deterministically from templates (seeded), written to JSONL so the
exact records are versioned with the repo. 182 records across 9 categories,
including a ``hard`` set the current heuristics are expected to miss.
Every record carries the *gold* final text/intent plus the terms that were
retracted (must not leak) and required (must appear), which is what the
intent-drift metric keys on.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from .schema import BenchRecord

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "voicehci_bench_v1.jsonl"

_FILLERS = ["um", "uh", "umm", "er"]
_NAMES = ["john", "jane", "priya", "marcus", "lena", "omar", "sophie", "dev"]
_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]
_TIMES = ["three", "four", "five", "noon", "ten", "4 PM", "2 PM"]
_TEAMS = ["marketing", "finance", "support", "design", "legal", "the on call"]
_STATES = ["ready", "blocked", "delayed", "shipped", "on hold", "merged"]
_CHAT_APPS = ["Slack", "WhatsApp", "Discord", "Teams"]
_DOC_APPS = ["Notion", "Google Docs", "Word", "Obsidian"]

_CLEAN = [
    ("the build is green and the release notes are drafted", "The build is green and the release notes are drafted."),
    ("can you review the pull request before standup", "Can you review the pull request before standup."),
    ("lunch is at noon in the main kitchen", "Lunch is at noon in the main kitchen."),
    ("the customer wants the invoice resent by friday", "The customer wants the invoice resent by friday."),
    ("I pushed the fix and the tests pass locally", "I pushed the fix and the tests pass locally."),
    ("please add the new logo to the landing page", "Please add the new logo to the landing page."),
    ("the latency regression is fixed in the latest build", "The latency regression is fixed in the latest build."),
    ("we should migrate the queue before the traffic spike", "We should migrate the queue before the traffic spike."),
    ("remind me to renew the domain next week", "Remind me to renew the domain next week."),
    ("the meeting notes are in the shared folder", "The meeting notes are in the shared folder."),
]


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _with_fillers(rng: random.Random, text: str, n: int) -> str:
    words = text.split()
    for _ in range(n):
        pos = rng.randint(1, max(1, len(words) - 1))
        words.insert(pos, rng.choice(_FILLERS))
    return " ".join(words)


def generate_dataset(seed: int = 7) -> list[BenchRecord]:
    rng = random.Random(seed)
    recs: list[BenchRecord] = []
    i = 0

    def add(**kw) -> None:
        nonlocal i
        i += 1
        kw.setdefault("kind", "dictation")
        recs.append(BenchRecord(id=f"vhb-{i:03d}", **kw))

    # -- clean (20)
    for k in range(20):
        spoken, gold = _CLEAN[k % len(_CLEAN)]
        app = rng.choice(_DOC_APPS) if k % 2 == 0 else rng.choice(_CHAT_APPS)
        gold_app = gold if app in _DOC_APPS else gold.rstrip(".")
        add(category="clean", spoken=spoken, app=app, expected_text=gold_app, difficulty=1)

    # -- filler (25)
    for k in range(25):
        spoken, gold = _CLEAN[k % len(_CLEAN)]
        app = rng.choice(_DOC_APPS)
        add(category="filler", spoken=_with_fillers(rng, spoken, 1 + k % 3), app=app,
            expected_text=gold, difficulty=1 + (k % 3 == 2))

    # -- pivot_restart (25): "send X to A ... no, send X to B"
    for k in range(25):
        a, b = rng.sample(_NAMES, 2)
        thing = rng.choice(["the report", "the deck", "the invoice", "the doc", "it"])
        pivot = rng.choice(["no", "no wait", "sorry", "actually", "I mean"])
        spoken = f"send {thing} to {a} {pivot} send {thing} to {b}"
        if k % 3 == 1:
            # anchor variant: "to b" replaces "to a at <time>", so the time is dropped too
            spoken = f"send {thing} to {a} at {rng.choice(_TIMES)} {pivot} to {b}"
        app = rng.choice(_CHAT_APPS)
        gold = f"Send {thing} to {b}"
        add(category="pivot_restart", spoken=spoken, app=app, expected_text=gold,
            retracted_terms=[a], required_terms=[b], difficulty=2)

    # -- pivot_complement (25): "the X is A ... actually make that B"
    for _ in range(25):
        subj = rng.choice(["the deployment", "the launch", "the migration", "the demo", "the release"])
        s1, s2 = rng.sample(_STATES, 2)
        pivot = rng.choice(["actually make that", "make that", "change that to", "I mean", "no wait",
                            "actually wait make that"])
        tail = rng.choice(["", " because QA found an edge case", " until " + rng.choice(_TIMES)])
        spoken = f"{subj} is {s1} {pivot} {s2}{tail}"
        app = rng.choice(_CHAT_APPS + _DOC_APPS)
        gold = _cap(f"{subj} is {s2}{tail}")
        if app in _DOC_APPS:
            gold += "."
        add(category="pivot_complement", spoken=spoken, app=app, expected_text=gold,
            retracted_terms=[s1.split()[0]], required_terms=[s2.split()[0]], difficulty=2)

    # -- scratch (20): "A scratch that B"
    for _ in range(20):
        d1, d2 = rng.sample(_DAYS, 2)
        pivot = rng.choice(["scratch that", "never mind", "delete that", "strike that"])
        lead = rng.choice(["let's meet", "the review is", "ship it", "demo day is"])
        spoken = f"{lead} on {d1} {pivot} {lead} on {d2}"
        app = rng.choice(_DOC_APPS)
        add(category="scratch", spoken=spoken, app=app, expected_text=_cap(f"{lead} on {d2}."),
            retracted_terms=[d1], required_terms=[d2], difficulty=2)

    # -- meta (20): commands
    metas = [
        ("action items new line bullet ship the patch new line bullet update the changelog",
         "Action items\n- Ship the patch\n- Update the changelog."),
        ("hi team period the build is green period", "Hi team. The build is green."),
        ("is the deck ready question mark", "Is the deck ready?"),
        ("first point new paragraph second point", "First point\n\nSecond point."),
        ("we shipped it exclamation mark", "We shipped it!"),
        ("notes colon the api is stable comma the ui is not", "Notes: the api is stable, the ui is not."),
        ("todo new line bullet fix login new line bullet write tests period",
         "Todo\n- Fix login\n- Write tests."),
        ("send the draft today delete the last word tomorrow", "Send the draft tomorrow."),
        ("this is wrong period delete the last sentence this is right period", "This is right."),
        ("the owner is dev capitalize that", "The owner is Dev."),
    ]
    for k in range(20):
        spoken, gold = metas[k % len(metas)]
        add(category="meta", spoken=spoken, app=rng.choice(_DOC_APPS), expected_text=gold,
            difficulty=2)

    # -- compound (15): fillers + pivot + command
    for _ in range(15):
        team1, team2 = rng.sample(_TEAMS, 2)
        spoken = (f"um action items new line bullet notify {team1} scratch that notify {team2} "
                  f"new line bullet uh ship the fix period")
        gold = f"Action items\n- Notify {team2}\n- Ship the fix."
        add(category="compound", spoken=spoken, app=rng.choice(_DOC_APPS), expected_text=gold,
            retracted_terms=[team1.split()[-1]], required_terms=[team2.split()[-1]], difficulty=3)

    # -- hard (12): adversarial corrections the rule-based resolver is NOT expected to ace.
    # These exist so the benchmark can fail. Expected outputs are what a human editor
    # would want; the gap is reported, not hidden.
    hard = [
        ("message john saying running late actually make that very late",
         "Message john saying running very late", ["late"], ["very"]),
        ("the api returns a list no a dict of users", "The api returns a dict of users.", ["list"], ["dict"]),
        ("we need three no four reviewers", "We need four reviewers.", ["three"], ["four"]),
        ("call him at five fifteen I mean five thirty", "Call him at five thirty.", ["fifteen"], ["thirty"]),
        ("the owner is dev actually it's priya", "The owner is priya.", ["dev"], ["priya"]),
        ("use the blue button no the green one", "Use the green button.", ["blue"], ["green"]),
        ("move it to q3 wait q4", "Move it to q4.", ["q3"], ["q4"]),
        ("tell the team the demo is at noon no wait at one", "Tell the team the demo is at one.", ["noon"], ["one"]),
        ("book the room for ten people actually twelve", "Book the room for twelve people.", ["ten"], ["twelve"]),
        ("ship it on friday or actually thursday", "Ship it on thursday.", ["friday"], ["thursday"]),
        ("the fix is in the auth module I mean the billing module", "The fix is in the billing module.",
         ["auth"], ["billing"]),
        ("rename it to foo bar no foo baz", "Rename it to foo baz.", ["bar"], ["baz"]),
    ]
    for spoken, gold, retracted, required in hard:
        app = "Slack" if not gold.endswith(".") else "Notion"
        add(category="hard", spoken=spoken, app=app, expected_text=gold, retracted_terms=retracted,
            required_terms=required, difficulty=3)

    # -- action (20): voice commands
    actions = [
        ("open slack", "open_app", {"app": "slack"}, {}),
        ("launch vs code", "open_app", {"app": "vscode"}, {}),
        ("open slag", "open_app", {"app": "slack"}, {}),  # ASR mishear
        ("fire up the terminal", "open_app", {"app": "terminal"}, {}),
        ("switch to chrome", "focus_window", {"app": "chrome"}, {}),
        ("go to spotify", "focus_window", {"app": "spotify"}, {}),
        ("search for faster whisper streaming", "search_web", {"query": "faster whisper streaming"}, {}),
        ("google accessibility tree latency", "search_web", {"query": "accessibility tree latency"}, {}),
        ("message john saying running late", "send_message", {"recipient": "john"}, {}),
        ("tell priya on slack that the build is green", "send_message", {"recipient": "priya", "app": "slack"}, {}),
        ("open slack and message jane saying lunch at noon", "open_app", {"app": "slack"}, {}),
        ("open notepad", "open_app", {"app": "notepad"}, {}),
        ("open crome", "open_app", {"app": "chrome"}, {"crome": "chrome"}),
        ("start discord", "open_app", {"app": "discord"}, {}),
        ("switch to the editor", "focus_window", {"app": "vscode"}, {}),
        ("look up windows ui automation", "search_web", {"query": "windows ui automation"}, {}),
        ("ping marcus saying can you review my pr", "send_message", {"recipient": "marcus"}, {}),
        ("open outlook", "open_app", {"app": "outlook"}, {}),
        ("undo that", "undo", {}, {}),
        ("open spotify no wait open slack", "open_app", {"app": "slack"}, {}),
    ]
    for spoken, intent, slots, rev in actions:
        retracted = ["spotify"] if "no wait" in spoken else []
        add(category="action", kind="action", spoken=spoken, app="desktop", expected_intent=intent,
            expected_slots=slots, asr_revisions=rev, retracted_terms=retracted, difficulty=2)

    return recs


def save_dataset(records: list[BenchRecord], path: Path = DEFAULT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")
    return path


def load_dataset(path: Path = DEFAULT_PATH) -> list[BenchRecord]:
    if not path.exists():
        recs = generate_dataset()
        save_dataset(recs, path)
        return recs
    with path.open(encoding="utf-8") as f:
        return [BenchRecord.from_dict(json.loads(line)) for line in f if line.strip()]
