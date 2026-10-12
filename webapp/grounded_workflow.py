"""Deterministic Agent Framework orchestration with grounded early exits."""

import asyncio
from collections.abc import Callable
from typing import Any

from agent_framework import WorkflowBuilder, WorkflowContext, executor


async def run_grounded_workflow(
    request: dict[str, Any],
    prepare_request: Callable[[dict[str, Any]], dict[str, Any]],
    retrieve_evidence: Callable[[dict[str, Any]], dict[str, Any]],
    answer_with_evidence: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    @executor(id="prepare")
    async def prepare(state: dict[str, Any], context: WorkflowContext[dict[str, Any], dict[str, Any]]) -> None:
        prepared = await asyncio.to_thread(prepare_request, state)
        if prepared.get("response") is not None:
            await context.yield_output(prepared["response"])
        else:
            await context.send_message(prepared)

    @executor(id="retrieve")
    async def retrieve(state: dict[str, Any], context: WorkflowContext[dict[str, Any], dict[str, Any]]) -> None:
        retrieved = await asyncio.to_thread(retrieve_evidence, state)
        if retrieved.get("response") is not None:
            await context.yield_output(retrieved["response"])
        else:
            await context.send_message(retrieved)

    @executor(id="answer_and_verify")
    async def answer(state: dict[str, Any], context: WorkflowContext[dict[str, Any], dict[str, Any]]) -> None:
        await context.yield_output(await asyncio.to_thread(answer_with_evidence, state))

    workflow = (
        WorkflowBuilder(name="dalil_grounded_rag", start_executor=prepare, output_from=[prepare, retrieve, answer])
        .add_edge(prepare, retrieve)
        .add_edge(retrieve, answer)
        .build()
    )
    result = await workflow.run(request)
    outputs = result.get_outputs()
    if len(outputs) != 1:
        raise RuntimeError("Grounded workflow must produce exactly one response")
    return outputs[0]