"""
Approval gate before PROD.
Blocks on stdin until a human explicitly types 'y'.
Agents must not auto-answer — enforced by SKILL.md guardrails.
"""


def require_approval(prompt: str) -> bool:
    """
    Prompts the developer in the terminal.
    Returns True only if they answer 'y' or 'yes'.
    """
    print(f"\n{prompt}")
    answer = input("Approve? (y/n): ").strip().lower()
    return answer in ("y", "yes")
