# AGENTS.md

This repository is a fresh explainable baseline for GPIC caption-to-concept extraction.

The priority is explainability, not maximum recall.

## Required Reading

Before creating or editing any code, lexicon, report, or documentation, read:

1. `AGENTS.md`
2. `docs/rules_v1.md`
3. `docs/answer_protocol.md`

If the requested change conflicts with `docs/rules_v1.md`, stop and explain the conflict before editing.

## Current Project State

This project has the explainable v1 pipeline implemented through Stage 6.

Future work must still follow the Rule Gate before adding or changing rules.

## Scope Boundary

Only the six-stage pipeline in `docs/rules_v1.md` is allowed:

1. caption shape judgment
2. spaCy preprocessing
3. spaCy linguistic annotation
4. raw concept extraction
5. canonicalization
6. count export

Do not add stages, hidden repairs, fallback chains, or extra lexicon families unless the user explicitly approves an update to `docs/rules_v1.md`.

## Rule Gate

Every extraction or transformation rule must be written in `docs/rules_v1.md` before implementation.

Each rule must state:

- rule id
- stage
- input
- output
- tool
- tool type
- rule type
- count impact
- known limitation

If a rule cannot be explained in this format, do not implement it.

## Allowed In V1

Allowed rule families are only:

- caption shape judgment: sentence vs tag-list
- spaCy tokenization
- raw quote span merge
- object MWE merge from explicit object lexicon
- plain hyphen word merge
- spaCy tagger
- object MWE POS correction
- spaCy dependency parser
- spaCy attribute ruler
- spaCy lemmatizer
- spaCy noun chunks
- noun chunk root to object
- noun chunk modifier to attribute or quantity
- VERB token to action
- `nsubj` child to agent
- `obj` or `dobj` child to patient
- ADP/preposition plus direct `pobj` to relation
- object synonym canonicalization
- attribute synonym and type canonicalization
- quantity raw-preserving canonicalization
- action synonym canonicalization
- parent concept mapping
- relation raw-preserving policy
- flat count export

## Forbidden In V1

Do not implement these in v1:

- pronoun resolution
- generic anaphora resolution
- `one`, `another`, `others`, `both` instance splitting
- passive voice normalization
- inherited agent repair
- skipped reference role recovery
- self-edge repair
- PP source disambiguation
- with-absolute recovery
- scene context fallback rules
- relation MWE collapse
- phrasal action collapse
- broad hidden hardcoded word lists inside Python code
- GPIC-error-specific patch rules
- any new linguistic interpretation during count export

## Implementation Rules

When implementation begins:

- keep functions small and single-purpose
- keep rule ids visible in output rows
- store lexicons as TSV files under `resources/lexicons`
- do not hide policy inside code comments
- do not copy logic from the previous prototype
- do not add a dependency without documenting why it is needed
- do not change generated reports by hand

## Communication Rules

When explaining this repository:

- use the six v1 stage numbers from `docs/rules_v1.md`
- distinguish implemented behavior from proposed behavior
- say "not implemented" when a feature is absent
- say "excluded by v1 design" when a feature is intentionally omitted
- do not describe this as high-recall

Use this description:

> an explainable caption-to-concept baseline with documented limitations

## Karpathy Guidelines

These behavioral guidelines reduce common LLM coding mistakes. They bias toward
caution over speed; for trivial tasks, use judgment.

### 1. Think Before Coding

Do not assume. Do not hide confusion. Surface tradeoffs.

Before implementing:

- state assumptions explicitly
- if uncertain, ask
- if multiple interpretations exist, present them rather than picking silently
- if a simpler approach exists, say so
- push back when warranted
- if something is unclear, stop, name what is confusing, and ask

### 2. Simplicity First

Write the minimum code that solves the problem. Do nothing speculative.

- no features beyond what was asked
- no abstractions for single-use code
- no flexibility or configurability that was not requested
- no error handling for impossible scenarios
- if 200 lines could be 50, rewrite it
- ask whether a senior engineer would call the solution overcomplicated; if yes,
  simplify it

### 3. Surgical Changes

Touch only what is necessary. Clean up only the mess created by the current
change.

When editing existing code:

- do not improve adjacent code, comments, or formatting
- do not refactor things that are not broken
- match existing style, even if a different style would be preferable
- if unrelated dead code is noticed, mention it rather than deleting it

When the current change creates orphans:

- remove imports, variables, or functions made unused by the current change
- do not remove pre-existing dead code unless asked

Every changed line must trace directly to the user's request.

### 4. Goal-Driven Execution

Define success criteria and loop until verified.

Transform tasks into verifiable goals:

- "Add validation" means write tests for invalid inputs, then make them pass.
- "Fix the bug" means write a test that reproduces it, then make it pass.
- "Refactor X" means ensure tests pass before and after.

For multi-step tasks, state a brief plan:

1. Step -> verify: check.
2. Step -> verify: check.
3. Step -> verify: check.

Strong success criteria allow independent progress. Weak criteria, such as
"make it work", require clarification.

## Evidence-Gated Answer Protocol

Follow `docs/answer_protocol.md` for any non-trivial explanation, especially
claims about current code behavior, runtime environment, GPU/CPU status,
benchmark speed, rule behavior, or generated outputs.

Do not present an inference as a verified fact.

When making a claim about the current repository or environment, separate:

- verified observation
- code/file evidence
- inference
- unknown or unchecked state

For code behavior:

- inspect the relevant file before explaining the implemented behavior
- cite the file path or function name in the answer
- say "not checked in this turn" if the file was not inspected

For runtime and benchmark claims:

- state the exact command or output file used as evidence
- state model, input size, batch size, stage range, intermediate-file policy,
  GPU/CPU status, and environment scope
- never infer hardware capability from one library's runtime status
- separate physical GPU availability, PyTorch CUDA availability, spaCy GPU/CuPy
  availability, and the actual device used in the latest run

Forbidden unless independently verified in the current turn:

- "this machine cannot use GPU"
- "only CPU is available"
- "the code currently does X" without reading the relevant code
- "the benchmark speed is X" without the command, input size, and stage range
