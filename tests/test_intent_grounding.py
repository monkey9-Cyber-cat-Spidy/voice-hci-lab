from voice_action.grounding import MockUIProvider, UINode, UITree, find_element
from voice_action.intent import Intent, StreamingIntentClassifier, resolve_app

cl = StreamingIntentClassifier()


def test_confidence_rises_as_slots_fill():
    c1 = cl.primary("open", final=False).confidence
    c2 = cl.primary("open slack", final=False).confidence
    assert c1 < 0.5 < c2
    assert cl.primary("open slack", final=False).slots == {"app": "slack"}


def test_compound_command():
    hyps = cl.classify("open slack and message john saying running late, start without me")
    assert [h.intent for h in hyps] == [Intent.OPEN_APP, Intent.SEND_MESSAGE]
    assert hyps[1].slots == {"recipient": "john", "body": "running late, start without me"}
    assert hyps[1].complete


def test_fuzzy_app_resolution():
    assert resolve_app("slag")[0] == "slack"
    assert resolve_app("vs code")[0] == "vscode"
    assert resolve_app("the editor")[0] == "vscode"
    assert resolve_app("xyzzy")[0] is None


def test_pivot_aware_classification():
    h = cl.primary("open spotify no wait open slack")
    assert h.intent is Intent.OPEN_APP and h.slots["app"] == "slack"
    # on a partial, the forming correction is deferred: still spotify for now
    h = cl.primary("open spotify no wait", final=False)
    assert h.slots["app"] == "spotify"


def test_misc_intents():
    assert cl.primary("search for faster whisper").slots == {"query": "faster whisper"}
    assert cl.primary("undo that").intent is Intent.UNDO
    assert cl.primary("never mind").intent is Intent.CANCEL
    assert cl.primary("move this file to archive").slots == {"dest": "archive"}
    assert cl.primary("switch to chrome").intent is Intent.FOCUS_WINDOW
    assert cl.primary("make me a sandwich").intent is Intent.UNKNOWN


def test_find_element_uses_role_hints_and_fuzzy_names():
    tree = UITree("slack", "Slack", [
        UINode("treeitem", "john", (0, 0, 10, 10)),
        UINode("edit", "Message #general", (0, 0, 10, 10), focused=True),
        UINode("button", "Send", (0, 0, 10, 10)),
        UINode("edit", "Search", (0, 0, 10, 10)),
    ])
    assert find_element(tree, "the message box").node.name == "Message #general"
    assert find_element(tree, "send button").node.role == "button"
    assert find_element(tree, "jon").node.name == "john"
    assert find_element(tree, "calendar") is None
    p = MockUIProvider(tree)
    p.snapshot()
    assert p.snapshots == 1
