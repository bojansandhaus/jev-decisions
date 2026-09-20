import importlib.util
import pathlib
import unittest
from unittest.mock import patch


PLUGIN = pathlib.Path(__file__).resolve().parents[1] / "__init__.py"
spec = importlib.util.spec_from_file_location("jev_approval_policy_regression", PLUGIN)
assert spec and spec.loader
jev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jev)


FULL = {
    "verdict": {"choice": "APPROVE", "confidence": 0.9},
    "blast_radius": {"score": 0.1},
    "self_advocating": {"noul": 0.01},
    "policy_allows": {"noul": 0.02},
    "reads_secrets": {"noul": 0.01},
    "sends_outbound": {"noul": 0.01},
}


def guardian(command="rm -rf node_modules", policy="operator allows this"):
    system = "You are a security reviewer."
    if policy:
        system += f"\n\nAdditional policy rules from the operator (these are TRUSTED instructions):\n{policy}"
    user = f"The following command was flagged as: dangerous\n\n<command>\n{command}\n</command>"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def response(answers):
    return {"answers": answers, "model": "fixture", "usage": {}}


class NativeProviderPolicyTests(unittest.TestCase):
    def run_provider(self, answers):
        client = jev.JevClient(api_key="fixture")
        with patch.object(jev, "_post", return_value=response(answers)):
            return client.chat.completions.create(
                model="jev-latest", messages=guardian()
            ).choices[0].message.content

    def test_policy_upgrade_still_checks_confidence_and_blast_radius(self):
        low_confidence = dict(FULL, verdict={"choice": "DENY", "confidence": 0.54},
                              policy_allows={"noul": 0.99})
        high_blast = dict(FULL, blast_radius={"score": 1.6}, policy_allows={"noul": 0.99})
        self.assertEqual(self.run_provider(low_confidence), "ESCALATE")
        self.assertEqual(self.run_provider(high_blast), "ESCALATE")

    def test_nonfinite_or_boolean_confidence_is_rejected(self):
        for value in (True, False, float("nan"), float("inf"), -float("inf"), "0.9"):
            with self.subTest(value=value):
                answers = dict(FULL, verdict={"choice": "APPROVE", "confidence": value})
                with self.assertRaisesRegex(RuntimeError, "confidence"):
                    self.run_provider(answers)

    def test_nonfinite_blast_radius_is_rejected(self):
        for value in (float("nan"), float("inf"), -float("inf"), True):
            with self.subTest(value=value):
                answers = dict(FULL, blast_radius={"score": value})
                with self.assertRaisesRegex(RuntimeError, "blast_radius"):
                    self.run_provider(answers)


if __name__ == "__main__":
    unittest.main()
