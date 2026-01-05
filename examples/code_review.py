"""
Code Review Pipeline Example - Typed API
4 nodes, 1 LLM call. Static analysis happens in code, AI provides final review.
"""

import ast
import asyncio

from pydantic import BaseModel

from eggai_clutch import Clutch, Terminate


async def mock_llm(prompt: str) -> str:
    return "[AI Review] Code looks clean. Consider adding type hints for better maintainability."


SAMPLE_CODE = """
def calculate_total(items):
    total = 0
    for item in items:
        total += item["price"] * item["quantity"]
    return total

def process_order(order):
    if order.status == "pending":
        order.status = "processing"
        send_notification(order.customer_email)
    return order
"""


class CodeReview(BaseModel):
    code: str
    functions: list[str] = []
    line_count: int = 0
    parse_success: bool = False
    parse_error: str = ""
    lint_issues: list[str] = []
    vulnerabilities: list[str] = []
    ai_review: str = ""


clutch = Clutch("code-review")


@clutch.agent()
async def parser(review: CodeReview) -> CodeReview:
    """Parse and extract metadata. Pure code."""
    try:
        tree = ast.parse(review.code)
        review.functions = [
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        ]
        review.line_count = len(review.code.split("\n"))
        review.parse_success = True
        print(f"    [Parser] Found {len(review.functions)} functions: {review.functions}")
    except SyntaxError as e:
        review.parse_success = False
        review.parse_error = str(e)
        print(f"    [Parser] Syntax error: {e}")
    return review


@clutch.agent()
async def linter(review: CodeReview) -> CodeReview:
    """Static analysis. Pure code (mock pylint)."""
    issues = []
    lines = review.code.split("\n")
    for i, line in enumerate(lines):
        if len(line) > 100:
            issues.append(f"Line {i + 1}: too long ({len(line)} chars)")
    review.lint_issues = issues
    print(f"    [Linter] Found {len(issues)} lint issues")
    return review


@clutch.agent()
async def security_scanner(review: CodeReview) -> CodeReview:
    """Vulnerability check. Pure code (mock bandit)."""
    vulns = []
    if "eval(" in review.code:
        vulns.append("Potential code injection via eval()")
    if "exec(" in review.code:
        vulns.append("Potential code injection via exec()")
    if "password" in review.code.lower() and "=" in review.code:
        vulns.append("Potential hardcoded password")
    review.vulnerabilities = vulns
    print(f"    [Security] Found {len(vulns)} security issues")
    return review


@clutch.agent()
async def ai_reviewer(review: CodeReview) -> CodeReview:
    """AI review with context. LLM call."""
    context = f"""
Code ({review.line_count} lines):
Functions: {review.functions}
Lint issues: {review.lint_issues}
Security issues: {review.vulnerabilities}
"""
    review.ai_review = await mock_llm(f"Review:\n{context}")
    print("    [AI Reviewer] Generated review")
    raise Terminate(review)


async def main():
    print("=" * 60)
    print("CODE REVIEW PIPELINE EXAMPLE (TYPED)")
    print("=" * 60)

    result = await clutch.run(CodeReview(code=SAMPLE_CODE))

    print("\n" + "-" * 60)
    print("Review completed!")
    print(f"  Functions: {result['functions']}")
    print(f"  Lint issues: {result['lint_issues']}")
    print(f"  Security issues: {result['vulnerabilities']}")
    print(f"  AI Review: {result['ai_review']}")
    print("-" * 60)


if __name__ == "__main__":
    asyncio.run(main())
