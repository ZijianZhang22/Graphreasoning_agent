# AdaMAST-guided Graph Control — V2 prototype

This prototype tests a stronger idea than "AdaMAST + graph reasoning":

**Learned failure knowledge controls the inference budget.**

Flow:

```text
graph query
  -> read learned failure taxonomy
  -> estimate failure risk
  -> LOW risk: 1 solver
  -> MEDIUM risk: 2 solvers
  -> HIGH risk: 2 solvers + critic
  -> executable NetworkX verification
  -> record failure
  -> update taxonomy
  -> next queries use learned failure knowledge
```

The main experimental distinction is:

- `no_taxonomy`: no cross-query failure memory; effectively cheap single-solver behavior.
- `taxonomy`: failure history is accumulated, converted into reusable prompt patches and a risk signal, and that risk signal dynamically changes how much LLM compute is spent.

This is **AdaMAST-inspired**, not the full AdaMAST implementation. It keeps the important research mechanism for the first experiment: cross-query failure accumulation + reusable failure knowledge. The next step is replacing `LearnedTaxonomy` with AdaMAST's real `start_session / record_trace / end_session` runtime.

## Colab quick start

```python
!git clone https://github.com/ZijianZhang22/Graphreasoning_agent.git
%cd Graphreasoning_agent
!pip install -r requirements.txt
!git clone https://github.com/Arthur-Heng/NLGraph external/NLGraph
```

If this repository is private, authenticate GitHub in Colab before cloning.

Set your API key in Colab:

```python
import os
os.environ["OPENAI_API_KEY"] = "YOUR_KEY"
```

Then run:

```python
!python run_experiment.py \
  --nlgraph-root external/NLGraph \
  --model gpt-4o-mini \
  --mode no_taxonomy \
  --num-examples 30
```

and:

```python
!python run_experiment.py \
  --nlgraph-root external/NLGraph \
  --model gpt-4o-mini \
  --mode taxonomy \
  --num-examples 30
```

Compare:
- `accuracy`
- `first_try_accuracy`
- `avg_calls_per_example`
- `repairs`
- `critics`
- input/output tokens
- latency

## What to look for

A useful early signal is not necessarily higher accuracy. It is:

- similar or higher accuracy,
- fewer average LLM calls than a fixed multi-agent policy,
- repeated failure types becoming less frequent,
- high-compute escalation concentrated on failure-prone query types.

## Important limitation

Connectivity is an easy debugging benchmark. To make the project research-worthy,
extend this to shortest path, cycle, topology, and then replace the simple
frequency-based `LearnedTaxonomy` with the actual AdaMAST taxonomy-generation
and refinement runtime.
