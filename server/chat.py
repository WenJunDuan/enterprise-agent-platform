"""Interactive multi-turn chat shell."""

from __future__ import annotations

from server.core import run_agent
from server.stores.session_store import new_conversation_id, resolve_latest_session_id


async def interactive_chat() -> None:
    conversation_id = new_conversation_id()
    print(f"Interactive conversation: {conversation_id[:8]}...")
    print("Type /quit to exit.\n")

    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if user_input in {"", "/quit", "/exit"}:
            break

        resume_session_id = resolve_latest_session_id(conversation_id)
        async for event in run_agent(
            user_input,
            conversation_id=conversation_id,
            resume_session_id=resume_session_id,
        ):
            if event["type"] == "text":
                print(f"agent> {event['content']}")
            elif event["type"] == "result":
                print(f"[done] {event['content']}")
        print()
