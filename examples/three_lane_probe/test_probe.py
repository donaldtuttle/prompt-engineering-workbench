"""Independent golden vectors captured from the original public browser UI."""

import copy
import json
import unittest

from probe import (
    CONDITIONS,
    CONTROL,
    DELIVERIES,
    DEMO,
    HANDSHAKE,
    TASK,
    assemble,
    fixture_call,
    inspect_demo,
    prompt_hash,
    run,
    serialize_messages,
)


class ProbeTests(unittest.TestCase):
    def test_source_default_prompt_hashes(self):
        expected = (
            "f510033cc46cd1b74dd5c88930b3002e61d6f860870b428462bcd7c6bb498f75",
            "d221cb1c4370524795d439b0b93f3c41b08c8db0485778c4875ebe0ccb7e8862",
            "936e94e6ccbed148b87bd8eef70c0068a0eeda4c7239e431a8e698795b7e935d",
        )
        for kind, golden in zip(CONDITIONS, expected, strict=True):
            self.assertEqual(prompt_hash(assemble(TASK, kind, "SYSTEM_SLOT")), golden)

    def test_source_handshake_initial_hash_prefixes(self):
        for kind, prefix in zip(
            CONDITIONS, ("098a829c6e90410a", "bcfd9867e0fe68da", "92ce85552ad7394e"), strict=True
        ):
            messages = assemble(TASK, kind, "USER_PASTE_WITH_HANDSHAKE")
            self.assertTrue(prompt_hash(messages).startswith(prefix))
            self.assertNotIn(TASK, serialize_messages(messages).decode())
            self.assertEqual(messages[-1]["content"], HANDSHAKE)

    def test_source_pasted_prompt_hashes(self):
        expected = (
            "f510033cc46cd1b74dd5c88930b3002e61d6f860870b428462bcd7c6bb498f75",
            "3684b6e27261bf9159d370cb288c5f6f15b90bd89ebabe1706209ff318cc1b4a",
            "49fd16848764406626aa097f5c79b951354cca16567d482b7a01cb0acaf7faf7",
        )
        for kind, golden in zip(CONDITIONS, expected, strict=True):
            self.assertEqual(prompt_hash(assemble(TASK, kind, "USER_PASTE")), golden)

    def test_tamper_blocks_context_without_repair(self):
        for delivery in DELIVERIES:
            result = run(delivery=delivery, tamper=True)
            self.assertEqual(
                [r["status"] for r in result["runs"]], ["SUCCEEDED", "BLOCKED", "BLOCKED"]
            )
            self.assertEqual(result["artifact"]["byte_length"], 172)
            self.assertIn("\r\n", result["artifact_text"])
            self.assertEqual(result["runs"][1]["calls"], [])
            self.assertEqual(result["runs"][2]["calls"], [])

    def test_call_counts_and_conversation_isolation(self):
        for delivery in DELIVERIES:
            result = run(delivery=delivery)
            expected = 2 if delivery == "USER_PASTE_WITH_HANDSHAKE" else 1
            self.assertEqual([len(r["calls"]) for r in result["runs"]], [expected] * 3)
            self.assertEqual(result["status"], "COMPLETED")
            for lane in result["runs"]:
                self.assertEqual(lane["calls"][-1]["messages"][-1]["content"], TASK)
            baseline = result["runs"][0]["calls"][-1]["messages"]
            self.assertNotIn(DEMO, [m["content"] for m in baseline])
            self.assertNotIn(CONTROL, [m["content"] for m in baseline])

    def test_boundary_rejects_mutated_prompt(self):
        messages = assemble(TASK, "BASELINE", "SYSTEM_SLOT")
        stored = prompt_hash(messages)
        messages[0]["content"] += " modified"
        with self.assertRaises(ValueError):
            fixture_call(messages, stored, "TASK", "BASELINE")

    def test_input_validation_and_unicode(self):
        for task in ("", "   ", "x" * 4001):
            with self.assertRaises(ValueError):
                run(task)
        with self.assertRaises(ValueError):
            run(delivery="unknown")
        task = 'Ξ / emoji 🧪 / "quotes" / newline\n'
        record = run(task)
        self.assertEqual(json.loads(record["runs"][0]["result"])["task_received"], task)
        self.assertIn("Ξ".encode(), serialize_messages(assemble(task, "BASELINE", "USER_PASTE")))

    def test_roles_and_exact_context_preservation(self):
        for delivery, role in (("SYSTEM_SLOT", "system"), ("USER_PASTE", "user")):
            messages = assemble(TASK, "FULL_INJECTOR", delivery)
            self.assertEqual(
                messages, [{"role": role, "content": DEMO}, {"role": "user", "content": TASK}]
            )

    def test_only_exact_fixture_is_valid(self):
        self.assertEqual(inspect_demo(DEMO.encode())["status"], "VALID")
        for raw in (
            b"\xff",
            b"",
            b"\xef\xbb\xbf" + DEMO.encode(),
            DEMO.replace("task", "TASK").encode(),
        ):
            self.assertEqual(inspect_demo(raw)["status"], "INVALID")

    def test_no_evaluation_or_model_inference(self):
        record = run()
        self.assertIsNone(record["evaluation"])
        self.assertIsNone(record["resolved_model"])
        self.assertEqual(record["resolution"], "INSUFFICIENT_EVIDENCE")
        self.assertNotEqual(record["schema_version"], "workbench-experiment-v2")
        for lane in record["runs"]:
            for call in lane["calls"]:
                self.assertIsNone(call["usage"])
                self.assertIsNone(call["cost"])

    def test_call_keeps_input_snapshot(self):
        messages = assemble(TASK, "BASELINE", "SYSTEM_SLOT")
        original = copy.deepcopy(messages)
        call = fixture_call(messages, prompt_hash(messages), "TASK", "BASELINE")
        messages[0]["content"] = "later edit"
        self.assertEqual(call["messages"], original)


if __name__ == "__main__":
    unittest.main()
