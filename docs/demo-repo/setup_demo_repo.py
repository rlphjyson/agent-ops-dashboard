"""One-time setup for the flagship demo fixture: turns this directory into a real, tiny git repo
with two commits -- the first with a correct calculator.add, the second introducing a subtle,
plausible-looking bug -- so the flagship demo task ("investigate why tests are failing in this
repo and file a GitHub issue summarizing the problem") has something real to investigate.

This directory ships as plain files, not a real git repo, deliberately: nesting one git repo
inside another (agent-ops-dashboard's own) is awkward (submodule-like gitlink handling) for no
real benefit here. Run this once locally instead:

    python docs/demo-repo/setup_demo_repo.py

Then point the flagship demo task at this directory's absolute path.
"""

import subprocess
from pathlib import Path

DEMO_DIR = Path(__file__).parent

CORRECT_CALCULATOR = """def add(a: int, b: int) -> int:
    return a + b


def multiply(a: int, b: int) -> int:
    return a * b
"""

BUGGY_CALCULATOR = """def add(a: int, b: int) -> int:
    return a - b


def multiply(a: int, b: int) -> int:
    return a * b
"""

TEST_FILE = """from calculator import add, multiply


def test_add():
    assert add(2, 3) == 5


def test_add_negative():
    assert add(-2, 3) == 1


def test_multiply():
    assert multiply(3, 4) == 12
"""


def run(*args: str) -> None:
    subprocess.run(["git", *args], cwd=DEMO_DIR, check=True)


def main() -> None:
    (DEMO_DIR / "tests").mkdir(exist_ok=True)
    (DEMO_DIR / "calculator.py").write_text(CORRECT_CALCULATOR, encoding="utf-8")
    (DEMO_DIR / "tests" / "test_calculator.py").write_text(TEST_FILE, encoding="utf-8")
    (DEMO_DIR / "tests" / "__init__.py").write_text("", encoding="utf-8")

    run("init", "-q")
    run("config", "user.email", "demo@example.com")
    run("config", "user.name", "Demo")
    run("add", "calculator.py", "tests/test_calculator.py", "tests/__init__.py")
    run("commit", "-q", "-m", "Add calculator with add() and multiply()")

    (DEMO_DIR / "calculator.py").write_text(BUGGY_CALCULATOR, encoding="utf-8")
    run("add", "calculator.py")
    run("commit", "-q", "-m", "Simplify add() implementation")

    print(f"Demo repo ready at {DEMO_DIR} -- 2 commits, 2 of 3 tests now fail.")


if __name__ == "__main__":
    main()
