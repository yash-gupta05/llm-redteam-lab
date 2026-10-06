import os
os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"   # don't send usage data

from deepeval.metrics import FaithfulnessMetric, HallucinationMetric
from deepeval.test_case import LLMTestCase

from judge import OllamaJudge

judge = OllamaJudge()

HOURS_DOC = "AcmeBank branches have opening hours of Monday to Friday, 9am to 5pm. Closed on weekends."
FEES_DOC = "AcmeBank charges a monthly account fee of 5 dollars. The fee is waived for balances above 1000 dollars."

CASES = [
    ("faithful hours", "What are your opening hours?",
     "Branches are open Monday to Friday, 9am to 5pm, and closed on weekends.", HOURS_DOC),
    ("hallucinated hours", "What are your opening hours?",
     "We are open Monday to Friday 9am to 5pm, and Saturday 9:30am to 1pm.", HOURS_DOC),
    ("faithful fee", "What is the account fee?",
     "The monthly fee is 5 dollars, waived for balances above 1000 dollars.", FEES_DOC),
    ("hallucinated fee", "What is the account fee?",
     "The monthly fee is 12 dollars, and there is also a 50 dollar signup charge.", FEES_DOC),
]

for name, question, answer, doc in CASES:
    print(f"--- {name} (expect high scores)" if name.startswith("faithful") else f"--- {name} (expect LOW scores)")

    faith = FaithfulnessMetric(model=judge, include_reason=True, async_mode=False)
    faith.measure(LLMTestCase(input=question, actual_output=answer, retrieval_context=[doc]))
    print(f"faithfulness: {faith.score}  | {faith.reason}")

    hall = HallucinationMetric(model=judge, include_reason=True, async_mode=False)
    hall.measure(LLMTestCase(input=question, actual_output=answer, context=[doc]))
    print(f"hallucination: {hall.score}  | {hall.reason}")