# ADR-003: LangGraph for Agent Orchestration over CrewAI / AutoGen
*Date: 2026-03-10 | Status: Accepted*

## Context

The platform requires a 9-agent pipeline with:
- Typed state passed between agents
- A Critic Agent that runs after every other agent (enforced topology)
- Conditional routing (e.g., Critic HARD block → stop pipeline)
- Checkpointing (resume pipeline from last successful agent on failure)
- Observability integration (LangSmith tracing)

Frameworks evaluated: LangGraph, CrewAI, AutoGen, custom Python DAG.

## Decision

Use LangGraph for agent orchestration.

## Rationale

| Requirement | LangGraph | CrewAI | AutoGen | Custom DAG |
|---|---|---|---|---|
| Typed state between agents | Yes — `TypedDict` or Pydantic | Partial — string-based message passing | Partial | Yes (but we build it) |
| Enforced topology (Critic after every node) | Yes — graph edges are explicit | No — agents collaborate ad-hoc | No — autonomous agents | Yes (but we build it) |
| Conditional routing on agent output | Yes — conditional edges | No | No | Yes |
| Pipeline checkpointing / resume | Yes — built-in | No | No | No |
| LangSmith integration | Yes — `@traceable`, native | Partial | No | No |
| Human-in-the-loop pause | Yes — `interrupt_before` | No | Partial | No |
| Async support | Yes | Partial | Yes | Yes |
| Production maturity (2026) | High | Medium | Medium | N/A |

### Why Critic Agent topology requires LangGraph

The Critic Agent runs after every agent. In CrewAI, agents collaborate through message passing — there is no mechanism to insert a mandatory validation step after every other agent without modifying every agent. In LangGraph, the Critic is a node connected by edges from every other node — the graph structure enforces this topologically. If a new agent is added, it must be connected to the Critic node before its edges reach the next agent. The graph cannot be compiled without this.

### Typed state

LangGraph's `StateGraph` requires a typed state schema. This forces every agent to define its output shape before it can be wired into the graph. This is a constraint, not a limitation — it prevents the raw-text-passing failure mode.

## Consequences

- Import paths: `from langgraph.graph import StateGraph, END` (v1.1.10 — compatible with 0.4.x agent code)
- State schema defined as Pydantic model per agent output
- Critic node wired after every other node — graph compilation fails if not
- LangGraph checkpointing enables pipeline resume from last successful agent

## Rejected Alternatives

- **CrewAI:** Ad-hoc collaboration model — no enforced topology, no typed state, no Critic-after-every-agent guarantee
- **AutoGen:** Conversational multi-agent — designed for chatbots, not deterministic evaluation pipelines
- **Custom DAG:** Valid but requires building checkpointing, observability integration, conditional routing from scratch — LangGraph provides all of these
