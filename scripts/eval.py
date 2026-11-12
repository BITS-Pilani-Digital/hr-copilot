"""Tiny evaluation harness: did we retrieve the right document, and does the answer contain the key fact + a citation?

Run:  python scripts/eval.py            (retrieval + answers, needs OPENAI_API_KEY)
      python scripts/eval.py --retrieval-only
"""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from copilot import config  # noqa: E402
from copilot.agent import HRCopilot  # noqa: E402
from copilot.hr_store import HRStore  # noqa: E402
from copilot.ingest import ensure_index, get_embedder  # noqa: E402
from copilot.retriever import Retriever  # noqa: E402

CASES = [
    {"q": "How many days of annual leave can I carry forward?", "source": "leave_policy.pdf", "expect": ["10"]},
    {"q": "When do I need a medical certificate for sick leave?", "source": "leave_policy.pdf", "expect": ["2"]},
    {"q": "How many weeks of paternity leave do I get?", "source": "leave_policy.pdf", "expect": ["4 weeks"]},
    {"q": "How many days a week must I be in the office?", "source": "remote_work_policy.pdf", "expect": ["3"]},
    {"q": "What is the home office allowance?", "source": "remote_work_policy.pdf", "expect": ["15,000"]},
    {"q": "What is the hotel limit in Bengaluru?", "source": "travel_expense_policy.pdf", "expect": ["7,000"]},
    {"q": "How long do I have to submit an expense claim?", "source": "travel_expense_policy.pdf", "expect": ["30"]},
    # Out-of-scope: the copilot should say it doesn't know instead of guessing.
    {"q": "What is the company's stock option vesting schedule?", "source": None,
     "expect_any": ["couldn't find", "could not find", "not find", "don't have", "do not have", "not covered", "hr-help"]},
]


def main(retrieval_only: bool) -> int:
    if not config.OPENAI_API_KEY:
        print("OPENAI_API_KEY is not set (add it to .env). The eval calls the real embedding/chat models.")
        return 2
    embedder = get_embedder()
    ensure_index(embedder)
    retriever = Retriever.load(embedder)
    with tempfile.TemporaryDirectory() as tmp:
        store = HRStore(requests_path=Path(tmp) / "requests.json")
        copilot = None if retrieval_only else HRCopilot(retriever, store, "E1001")
        passed = 0
        for case in CASES:
            hits = retriever.search(case["q"])
            retrieval_ok = case["source"] is None or any(h["source"] == case["source"] for h in hits)
            ok, note = retrieval_ok, f"top={hits[0]['source'] if hits else '-'}"
            if copilot:
                answer = copilot.ask(case["q"]).answer
                low = answer.lower()
                if case["source"]:
                    answer_ok = all(e.lower() in low for e in case["expect"]) and ".pdf" in low
                else:
                    answer_ok = any(e in low for e in case["expect_any"])
                ok = ok and answer_ok
                note += f" | answer: {answer[:110].replace(chr(10), ' ')}"
            passed += ok
            print(f"{'PASS' if ok else 'FAIL'}  {case['q']}  ({note})")
    print(f"\n{passed}/{len(CASES)} passed")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieval-only", action="store_true")
    sys.exit(main(parser.parse_args().retrieval_only))
