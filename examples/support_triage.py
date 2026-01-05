"""
Customer Support Triage Example - Typed API
Uses Selector strategy for dynamic routing based on intent classification.
"""

import asyncio

from pydantic import BaseModel

from eggai_clutch import Clutch, Strategy, Terminate


async def mock_llm(prompt: str) -> str:
    if "billing" in prompt.lower():
        return "[AI] Your recent charge of $49.99 was for the premium subscription renewal."
    elif "technical" in prompt.lower():
        return "[AI] Try clearing your cache and cookies, then restart the app."
    else:
        return "[AI] Thank you for contacting us. A support agent will be with you shortly."


class MockDB:
    @staticmethod
    async def get_account(user_id: str) -> dict:
        return {"user_id": user_id, "plan": "premium", "balance": 0, "last_charge": "$49.99"}

    @staticmethod
    async def search_issues(query: str) -> list:
        return ["Known issue #1234: App crashes on startup - fix deployed"]

    @staticmethod
    async def create_ticket(content: str, priority: str):
        print(f"    [DB] Created {priority} priority ticket: {content[:30]}...")


class SupportTicket(BaseModel):
    query: str
    user_id: str = ""
    response: str = ""
    category: str = ""


clutch = Clutch("support", Strategy.SELECTOR, max_turns=5)


@clutch.selector()
async def classifier(ticket: SupportTicket) -> str:
    """Route based on intent. Rule-based classification."""
    query = ticket.query.lower()

    if any(w in query for w in ["refund", "charge", "bill", "payment"]):
        print("    [Classifier] Routing to: billing")
        return "billing"
    elif any(w in query for w in ["bug", "error", "crash", "not working"]):
        print("    [Classifier] Routing to: technical")
        return "technical"
    elif any(w in query for w in ["cancel", "close account", "delete"]):
        print("    [Classifier] Routing to: retention")
        return "retention"
    else:
        print("    [Classifier] Routing to: general")
        return "general"


@clutch.agent()
async def billing(ticket: SupportTicket) -> SupportTicket:
    """Handle billing inquiries."""
    account = await MockDB.get_account(ticket.user_id or "user123")
    ticket.response = await mock_llm(f"Billing help: {ticket.query}\nAccount: {account}")
    ticket.category = "billing"
    print("    [Billing] Generated response")
    raise Terminate(ticket)


@clutch.agent()
async def technical(ticket: SupportTicket) -> SupportTicket:
    """Handle technical issues."""
    known_issues = await MockDB.search_issues(ticket.query)
    ticket.response = await mock_llm(
        f"Technical help: {ticket.query}\nKnown issues: {known_issues}"
    )
    ticket.category = "technical"
    print("    [Technical] Generated response")
    raise Terminate(ticket)


@clutch.agent()
async def retention(ticket: SupportTicket) -> SupportTicket:
    """Handle account cancellation requests."""
    await MockDB.create_ticket(ticket.query, priority="high")
    ticket.response = "Your request has been escalated to our retention team."
    ticket.category = "retention"
    print("    [Retention] Escalated to retention team")
    raise Terminate(ticket)


@clutch.agent()
async def general(ticket: SupportTicket) -> SupportTicket:
    """Handle general inquiries."""
    ticket.response = await mock_llm(f"General help: {ticket.query}")
    ticket.category = "general"
    print("    [General] Generated response")
    raise Terminate(ticket)


async def main():
    print("=" * 60)
    print("CUSTOMER SUPPORT TRIAGE EXAMPLE (TYPED)")
    print("=" * 60)

    test_cases = [
        ("I was charged twice for my subscription", "user001"),
        ("The app keeps crashing when I open it", "user002"),
        ("I want to cancel my account", "user003"),
        ("Hello, I have a question", "user004"),
    ]

    for query, user_id in test_cases:
        print(f'\n[Query] "{query}"')
        result = await clutch.run(SupportTicket(query=query, user_id=user_id))
        print(f"  Category: {result['category']}")
        print(f"  Response: {result['response'][:60]}...")

    print("\n" + "-" * 60)
    print("All support queries processed!")
    print("-" * 60)


if __name__ == "__main__":
    asyncio.run(main())
