# Dalil Web Application

See the [project README](../README.md) for setup, corpus, deployment and limitations.

- `main.py`: FastAPI and deterministic grounded-answer stages.
- `agent_runtime.py`: Microsoft Agent Framework model execution.
- `grounded_workflow.py`: preparation, retrieval, answer/verification workflow.
- `foundry_retrieval.py`: Foundry IQ results and allowlisted citations.
- `retrieval_fusion.py`: result fusion and document diversity.
- `demo_limits.py`: bounded body, request-rate and concurrency controls.
- `assets/`: bilingual Fluent-inspired Dalil interface and custom Dalil mark.

Run one worker; the public-demo limiter is process-local. The application has no
default cloud endpoints. Without configuration, `/healthz` returns 200 and
`/api/chat` returns a configuration error instead of fabricated answers.