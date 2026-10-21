"""Context Compactor — manages token budgets and compacts conversation history."""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Fast approximate token count (1 token ≈ 4 chars for English)."""
    return max(1, len(text) // 4)


def compact_messages(
    messages: list[dict[str, str]],
    max_tokens: int,
    threshold: float = 0.70,
) -> list[dict[str, str]]:
    """Compact conversation messages if total tokens exceed threshold."""
    total = sum(estimate_tokens(m.get("content", "")) for m in messages)

    if total <= int(max_tokens * threshold):
        return messages

    protected_tail = 4
    if len(messages) <= protected_tail + 1:
        return messages

    compacted = [messages[0]]
    middle = messages[1:-protected_tail]
    tail = messages[-protected_tail:]

    for msg in middle:
        content = msg.get("content", "")
        if len(content) > 500:
            truncated = content[:200] + "\n...[truncated]..."
            compacted.append({**msg, "content": truncated})
        else:
            compacted.append(msg)

    compacted.extend(tail)
    return compacted
