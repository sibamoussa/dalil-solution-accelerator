import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "webapp"))
from grounded_workflow import run_grounded_workflow


class GroundedWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_stages_execute_in_order(self):
        calls = []

        def prepare(state):
            calls.append("prepare")
            return {**state, "question": state["message"]}

        def retrieve(state):
            calls.append("retrieve")
            return {**state, "evidence": ["source"]}

        def answer(state):
            calls.append("answer")
            return {"answer": state["question"], "sources": state["evidence"]}

        result = await run_grounded_workflow({"message": "question"}, prepare, retrieve, answer)
        self.assertEqual(calls, ["prepare", "retrieve", "answer"])
        self.assertEqual(result, {"answer": "question", "sources": ["source"]})

    async def test_abstention_short_circuits_later_stages(self):
        for stage in ("prepare", "retrieve"):
            with self.subTest(stage=stage):
                abstention = {"abstained": True}
                prepare = Mock(return_value={"response": abstention} if stage == "prepare" else {})
                retrieve = Mock(return_value={"response": abstention})
                answer = Mock()
                self.assertEqual(await run_grounded_workflow({}, prepare, retrieve, answer), abstention)
                answer.assert_not_called()
                if stage == "prepare":
                    retrieve.assert_not_called()

    async def test_retrieval_error_is_not_an_empty_answer(self):
        from fastapi import HTTPException
        retrieve = Mock(side_effect=HTTPException(503, "Unavailable"))
        with self.assertRaises(HTTPException) as failure:
            await run_grounded_workflow({}, Mock(return_value={}), retrieve, Mock())
        self.assertEqual(failure.exception.status_code, 503)