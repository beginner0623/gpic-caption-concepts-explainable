# AGENTS.md

This repository is a fresh explainable baseline for GPIC caption-to-concept extraction.

The priority is explainability, not maximum recall.

## Required Reading

Before creating or editing any code, lexicon, report, or documentation, read:

1. `AGENTS.md`
2. `docs/rules_v1.md`

If the requested change conflicts with `docs/rules_v1.md`, stop and explain the conflict before editing.

## Current Project State

This project is in the explainable v1 pipeline implementation phase.

Stages 1-5 are implemented. Stage 6 count export is the next implementation target.

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
