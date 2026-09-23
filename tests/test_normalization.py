from tracelab.inspect_adapter.normalize import normalize_sample


def test_model_tool_events_preserve_raw_and_do_not_duplicate_tool_results():
    user = {"id": "u", "role": "user", "content": "Fix it", "unknown_message_field": 1}
    assistant = {
        "id": "a",
        "role": "assistant",
        "content": [{"type": "reasoning", "reasoning": "Investigate"}],
        "tool_calls": [{"id": "c", "function": "bash", "arguments": {"command": "pwd"}}],
    }
    tool = {
        "role": "tool",
        "tool_call_id": "c",
        "function": "bash",
        "content": "/workspace",
    }
    sample = {
        "unknown_sample_field": {"kept": True},
        "events": [
            {
                "event": "model",
                "input": [user],
                "output": {"choices": [{"message": assistant}]},
                "future_field": 42,
            },
            {
                "event": "tool",
                "id": "c",
                "function": "bash",
                "arguments": {"command": "pwd"},
                "result": "/workspace",
                "unmapped": [1, 2],
            },
            {
                "event": "model",
                "input": [user, assistant, tool],
                "output": {"choices": [{"message": {"role": "assistant", "content": "Done"}}]},
            },
            {"event": "new_future_type", "unfamiliar": {"anything": True}},
        ],
    }
    events, records = normalize_sample("t", sample)
    assert [e.type for e in events] == [
        "user",
        "reasoning",
        "tool_call",
        "tool_result",
        "assistant",
        "other",
    ]
    assert records[0]["raw"]["future_field"] == 42
    assert records[1]["raw"]["unmapped"] == [1, 2]
    assert records[-1]["raw"]["unknown_sample_field"]["kept"]
    assert events[-1].metadata["inspectType"] == "new_future_type"
    assert [e.index for e in events] == list(range(6))
    assert all(e.parent_event_ids == [events[i - 1].id] for i, e in enumerate(events) if i)


def test_partial_assistant_parts_have_no_future_content(event_factory):
    sample = {
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {"type": "reasoning", "reasoning": "first"},
                    {"type": "text", "text": "later"},
                ],
                "tool_calls": [{"id": "c", "function": "bash", "arguments": {"command": "later"}}],
            }
        ]
    }
    events, _ = normalize_sample("t", sample)
    from tracelab.forks.context import context_messages

    context = context_messages([events[0].wire()], [])
    assert context[0]["content"] == [{"type": "reasoning", "reasoning": "first"}]
    assert not context[0]["tool_calls"]
