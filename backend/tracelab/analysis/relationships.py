"""Recorded relationships only. A parent edge is not necessarily communication."""


def relationships(events):
    by_id = {e.event_id: e for e in events}
    edges = []
    for e in events:
        recipient = e.metadata.get("recipientAgentId")
        relation = e.metadata.get("relationshipType")
        if (
            isinstance(recipient, str)
            and e.agent_id
            and recipient != e.agent_id
            and relation in ("message_transfer", "delegation")
        ):
            edges.append(
                {
                    "id": f"envelope:{e.event_id}:{recipient}",
                    "kind": relation,
                    "sourceEventId": e.event_id,
                    "destinationEventId": e.event_id,
                    "sourceIndex": e.index,
                    "destinationIndex": e.index,
                    "sourceAgent": e.agent_id,
                    "destinationAgent": recipient,
                    "description": "Recorded sender/recipient envelope; both endpoints cite the same message, not an inferred receiving event",
                }
            )
        for pid in e.parent_ids:
            parent = by_id.get(pid)
            if parent and parent.agent_id and e.agent_id and parent.agent_id != e.agent_id:
                edges.append(
                    {
                        "id": f"{pid}->{e.event_id}",
                        "kind": "parent_event",
                        "sourceEventId": pid,
                        "destinationEventId": e.event_id,
                        "sourceIndex": parent.index,
                        "destinationIndex": e.index,
                        "sourceAgent": parent.agent_id,
                        "destinationAgent": e.agent_id,
                        "description": "Recorded parent relationship; does not by itself establish message transfer",
                    }
                )
    # Shared artifact references establish association, not directional communication.
    artifacts = {}
    for e in events:
        for ref in e.artifacts:
            key = (
                ref
                if isinstance(ref, str)
                else ref.get("id") or ref.get("uri")
                if isinstance(ref, dict)
                else None
            )
            if key:
                old = artifacts.get(key)
                if old and old.agent_id and e.agent_id and old.agent_id != e.agent_id:
                    edges.append(
                        {
                            "id": f"artifact:{key}:{old.event_id}:{e.event_id}",
                            "kind": "shared_artifact",
                            "sourceEventId": old.event_id,
                            "destinationEventId": e.event_id,
                            "sourceIndex": old.index,
                            "destinationIndex": e.index,
                            "sourceAgent": old.agent_id,
                            "destinationAgent": e.agent_id,
                            "description": f"Both events reference {key}; transfer direction unknown",
                        }
                    )
                artifacts[key] = e
    return edges
