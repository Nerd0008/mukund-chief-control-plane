# E3 Model Roster Handover — 2026-09-22

## Purpose

This handover captures the model-selection decisions for **E3**, the dynamic model scheduler/manager in Mukund's Chief of Staff / Chief Control Plane project.

The next implementation chat should treat this as the current model roster and architecture direction.

---

## Core E3 Principle

**Do not hardcode “model X is always used for task Y.”**

E3 should reason about each incoming task, decompose it when useful, assess the requirements of each subtask, and dynamically select the best available model or combination of models.

Model capability descriptions are **routing metadata**, not fixed routing rules.

E3 should consider factors such as:

- task type and complexity
- reasoning depth required
- coding / repository work
- tool and function calling
- vision / multimodal requirements
- GUI / computer-use requirements
- context-window requirements
- expected latency
- API cost
- cache pricing / cache availability
- provider quota / rate limits
- current model availability / health
- historical performance on similar tasks
- confidence / uncertainty
- need for independent verification
- required quality floor

For complex work, E3 may:

1. analyse the request,
2. split it into subtasks,
3. assign different subtasks to different models,
4. run workers in parallel when beneficial,
5. ask another model to critique or verify outputs,
6. synthesize the final result.

The scheduler itself may use AI reasoning to decide which models should handle each task.

If E3 encounters an error, ambiguous failure, broken dependency, or situation it cannot safely resolve, it should **escalate / ask Mukund rather than silently fail, loop indefinitely, or make a risky assumption**.

---

# Final 10-Model Pool

| # | Model / Worker | Current Status | Capability Profile / Why It Is Included |
|---|---|---|---|
| 1 | **Codex CLI** | LOCKED | Coding, repository work, implementation, debugging and software-engineering tasks. Counts as one E3 worker. Codex CLI may internally choose the appropriate GPT/Codex model and reasoning level. |
| 2 | **Mistral Small 4** | LOCKED | Low-cost independent provider; general reasoning, instruction following, coding, function calling, agents and structured outputs. Replaced Gemini Flash. |
| 3 | **Google Nano Banana 2** | LOCKED | Dedicated image generation and image-editing worker. Mukund already has a Google API key available for this. |
| 4 | **DeepSeek V4.1 Flash** | LOCKED | Very strong cost/performance for reasoning, coding, long-context work and agentic execution. Important high-capability, low-cost worker. |
| 5 | **GLM-5.3 Flash** | LOCKED | Very cheap high-volume reasoning/agent worker with strong tool-use and professional-workflow potential. Good candidate for large volumes of routine and parallel work. |
| 6 | **Qwen3.8-27B** | LOCKED | Multimodal / vision-heavy worker; useful for screenshots, documents, web/GUI understanding and computer-use-style tasks. |
| 7 | **LongCat 2.0** | EVALUATE / KEEP IN POOL | Existing Chief/Hermes model candidate. Retain while E3 benchmarking and provider integration are completed. |
| 8 | **MiniMax M3** | BENCHMARK | Low-cost general/agent candidate. Keep available for empirical comparison against DeepSeek/GLM/Mistral. |
| 9 | **Step 3.7 Flash** | BENCHMARK | Fast reasoning/agent candidate. Potential low-latency parallel worker; benchmark before assigning a permanent niche. |
| 10 | **Tencent Hunyuan Hy3** | BENCHMARK | Very inexpensive reasoning/coding/tool-use alternative and useful provider-diversity candidate. |

---

## Explicit Decisions Already Made

### Removed / not selected

- **Claude** — removed because API cost is too high for the intended multi-model architecture.
- **Gemini 3.8 Flash** — removed from the roster; **Mistral Small 4** replaces it.
- **Kimi K3** — not currently selected because its output-token cost is difficult to justify against the cheaper Chinese alternatives.
- Do not add duplicate GPT models as separate slots simply to increase the model count.

### GPT / OpenAI handling

GPT-family coding capability should be accessed through **Codex CLI**.

**Codex CLI counts as one E3 worker slot.**

E3 should treat Codex CLI as the worker/interface and allow Codex to choose the most appropriate underlying GPT/Codex model or reasoning level where supported.

### Image generation

Use **Google Nano Banana 2** as the dedicated image-generation/editing worker.

Mukund already has the necessary Google API key.

---

# Why These Models

The pool is intentionally heterogeneous.

It gives E3 access to:

- a specialist software-engineering route through Codex CLI,
- an independent low-cost Western model through Mistral,
- dedicated image generation through Nano Banana,
- multiple extremely cost-efficient Chinese reasoning/agent models,
- multimodal / visual reasoning through Qwen,
- multiple providers for resilience and quota failover,
- several benchmark candidates that can earn or lose their place based on real E3 telemetry.

The objective is **not** to make every model permanent forever.

The objective is to give E3 a strong initial pool, then allow measured performance to inform future roster changes.

---

# Important Routing Architecture

Do **not** implement a static map such as:

```text
coding -> DeepSeek
research -> GLM
vision -> Qwen
```

That would defeat the purpose of E3.

Instead, maintain a **capability registry** for every worker. Example fields:

```yaml
model_id:
provider:
interface:
enabled:
capabilities:
  reasoning:
  coding:
  vision:
  image_generation:
  tool_use:
  structured_output:
  computer_use:
context_window:
pricing:
  input_per_million:
  output_per_million:
  cached_input_per_million:
latency_class:
quota:
health:
historical_performance:
```

E3's decision layer should inspect task requirements and the live registry before choosing workers.

---

# Suggested E3 Decision Flow

```text
User / Chief task
      |
      v
Understand intent and constraints
      |
      v
Determine whether decomposition is useful
      |
      +----------------------+
      |                      |
      v                      v
 Single task             Subtasks
      |                      |
      +----------+-----------+
                 |
                 v
      Build capability requirements
                 |
                 v
      Inspect live model registry
      - capability
      - quality floor
      - context
      - cost
      - latency
      - quota
      - health
      - prior performance
                 |
                 v
      Select best worker(s)
                 |
        +--------+---------+
        |                  |
        v                  v
    Execute            Parallel execute
        |                  |
        +--------+---------+
                 |
                 v
       Verify / critique if needed
                 |
                 v
            Synthesize
                 |
                 v
         Return / take action
                 |
                 v
       Log outcome + telemetry
```

---

# Multi-Model Behaviour

E3 should be able to deliberately use more than one model when doing so improves reliability.

Examples:

### Complex coding job

```text
Task analysis
   -> Codex CLI + DeepSeek candidates
   -> implementation worker
   -> independent verification
   -> final synthesis / patch
```

### Large research / office workflow

```text
GLM / Mistral parallel extraction
   -> DeepSeek reasoning pass
   -> verifier
   -> synthesis
```

### Visual / computer task

```text
Qwen visual analysis
   -> reasoning/tool worker
   -> verification
```

These are **examples only**, not routing rules.

---

# Cost Philosophy

The low prices of DeepSeek, GLM, Step, Hunyuan and similar workers make multi-agent execution economically practical.

E3 therefore should not optimise solely for the **fewest API calls**.

It should optimise for:

**required quality + reliability + latency + available resources + sensible cost.**

For difficult tasks, several inexpensive independent calls plus a verifier may be preferable to a single expensive call.

Caching should be used aggressively when supported.

---

# Resource / Quality Integration

E3 must integrate with the broader Chief Control Plane resource-governor philosophy.

Important requirements:

- keep a required quality floor for the task,
- check provider/model capacity before dispatch,
- preserve protected capacity for active jobs / handovers,
- avoid silently downgrading quality merely because a preferred model is unavailable,
- support checkpoint -> state capture -> worker handover -> resume,
- monitor model/provider health,
- log cost and quota consumption,
- eventually learn from historical success/failure data.

If an equivalent worker is unavailable and continuing would violate the required quality floor, pause/escalate rather than silently producing degraded output.

---

# Benchmark Lane

The following models should initially be measured rather than trusted based only on published benchmarks:

- LongCat 2.0
- MiniMax M3
- Step 3.7 Flash
- Tencent Hunyuan Hy3

Benchmark them on **actual Chief-of-Staff workloads**, not only generic academic benchmarks.

Suggested test categories:

1. task decomposition quality
2. coding / debugging
3. repository comprehension
4. web/research synthesis
5. tool-selection accuracy
6. function-calling reliability
7. long-context instruction retention
8. document analysis
9. vision / screenshot understanding
10. planning quality
11. hallucination / unsupported-claim rate
12. multi-turn agent reliability
13. latency
14. cost per successful task
15. recovery after tool/model failure

Record results in E3 telemetry so the scheduler can eventually use empirical performance rather than a manually maintained opinion of which model is "best."

---

# Immediate E3 Implementation Priorities

1. Build the model/provider registry.
2. Add adapters for the locked models first.
3. Represent pricing, context limits, modality, tool support, latency and quota in machine-readable form.
4. Build the AI-powered task analyser/decomposer.
5. Build candidate-model selection.
6. Add multi-model / parallel execution.
7. Add verifier / critic selection.
8. Add synthesis.
9. Add model health + provider quota checks.
10. Add structured failure escalation.
11. Log every routing decision and outcome.
12. Use telemetry later to improve selection automatically.

---

# Current Decision Snapshot

**Roster size:** 10 workers/models.

**Locked:**
1. Codex CLI
2. Mistral Small 4
3. Google Nano Banana 2
4. DeepSeek V4.1 Flash
5. GLM-5.3 Flash
6. Qwen3.8-27B

**Benchmark / evaluation lane:**
7. LongCat 2.0
8. MiniMax M3
9. Step 3.7 Flash
10. Tencent Hunyuan Hy3

This is the roster the E3 implementation chat should begin from unless Mukund explicitly changes it.

---

## Handover instruction for the next chat

Continue with **E3 implementation**, using this file as the current model-selection authority.

Do not reopen the entire model-selection discussion unless:
- an integration is unavailable,
- pricing/capabilities materially changed,
- a selected model fails benchmarking,
- or Mukund asks to revisit the roster.

The next implementation step should be to translate this roster into the model registry/provider-adapter design used by E3.