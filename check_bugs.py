#!/usr/bin/env python3
"""
Bug checker for dashboard.py using Claude Agent SDK.

Usage:
    python check_bugs.py                    # Review dashboard.py
    python check_bugs.py path/to/file.py    # Review a specific file
"""

import sys
import anyio
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, SystemMessage

TARGET_FILE = sys.argv[1] if len(sys.argv) > 1 else "dashboard.py"

SYSTEM_PROMPT = """\
You are a senior Python bug reviewer. Your job is to find REAL bugs — not style issues.

Focus on:
1. **Runtime errors**: Variables used before definition, missing imports, wrong arguments, type errors
2. **Data bugs**: Operations that fail with empty/null data, division by zero, wrong aggregations
3. **Logic bugs**: Conditions always true/false, off-by-one, wrong sort order, broken filters
4. **Edge cases**: Empty DataFrames, missing columns, NaN propagation, API response changes

For each bug, report:
- **Line(s)**: exact line numbers
- **Bug**: what's wrong
- **Impact**: crash / wrong data / cosmetic
- **Fix**: concrete code suggestion

Do NOT report:
- Style preferences or formatting
- "Could be improved" suggestions
- Theoretical issues that require impossible conditions
- Deprecation warnings from third-party libraries

End with a summary table: | # | Severity | Line(s) | Description |
"""

async def main():
    print(f"🔍 Reviewing {TARGET_FILE} for bugs...\n")

    async for message in query(
        prompt=f"Read and review {TARGET_FILE} for bugs. Be thorough — read the entire file.",
        options=ClaudeAgentOptions(
            cwd="/Users/aleistermontfort/Documentos_HD/TIMESHEET_ANALYTICS",
            allowed_tools=["Read", "Glob", "Grep"],
            system_prompt=SYSTEM_PROMPT,
            max_turns=15,
        ),
    ):
        if isinstance(message, ResultMessage):
            print(message.result)

anyio.run(main)
