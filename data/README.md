# data: VoiceHCI-Bench Evaluation Dataset Specification

## Abstract

Machine learning benchmarks require open, structured, and auditable data artifacts. `data/voicehci_bench_v1.jsonl` provides 182 curated and deterministically generated evaluation records representing realistic conversational human speech patterns across desktop computing scenarios.

---

## 1. Dataset Generation Methodology

The dataset is generated deterministically by `voicehci_bench/dataset.py` using a fixed pseudo-random seed (`seed=7`). This guarantees that test distributions are reproducible across different research environments without relying on third-party data downloads.

To regenerate the dataset from source templates:
```bash
python -m voicehci_bench.cli dataset --seed 7
```

---

## 2. Category Distribution and Linguistic Taxonomy

The dataset partitions 182 records across 9 distinct categories:

| Category | Record Count | Target Behavioral Domain |
| :--- | :---: | :--- |
| `clean` | 20 | Baseline fluent conversational English; tests zero false-positive pivot activations. |
| `filler` | 20 | Natural discourse markers (`um`, `uh`, `er`, `like`); tests non-destructive stripping. |
| `pivot_restart` | 20 | Complete clause restarts (*"send it to john... no, send it to jane"*); tests syntactic prefix matching. |
| `pivot_complement` | 25 | Predicate updates (*"ready... make that delayed"*); tests copula and preposition anchoring. |
| `scratch` | 20 | Retraction directives (*"scratch that"*); tests single and multi-sentence clause deletion. |
| `meta` | 20 | Spoken punctuation and layout (*"new line"*, *"bullet"*, *"period"*); tests formatting boundaries. |
| `compound` | 25 | Chained multi-intent workflows (*"open slack and message john... then switch to vs code"*). |
| `hard` | 12 | Syntactically ambiguous adversarial edge cases; intentionally establishes heuristic failure modes. |
| `action` | 20 | Native desktop application manipulation (open, switch, search, move, undo). |

---

## 3. Schema Specification (JSON Lines Format)

Every record is stored as a single-line JSON object matching the following structure:

```json
{
  "record_id": "pivot_complement_004",
  "category": "pivot_complement",
  "spoken": "the demo is on hold actually wait make that merged",
  "expected": "The demo is merged",
  "app": "Slack",
  "revisions": null
}
```

### Field Descriptions
- **`record_id` (string)**: Globally unique identifier encoding the category and sequence index.
- **`category` (string)**: Category key used for segmented performance aggregation.
- **`spoken` (string)**: The simulated input utterance containing raw disfluencies, filler words, or directives.
- **`expected` (string or dictionary)**:
  - For dictation categories: The gold-standard formatted output string expected in the active text field.
  - For action categories: A structured dictionary specifying expected intent, slot bindings, and execution targets.
- **`app` (string)**: Target application environment (`Slack`, `Notion`, `VS Code`), directing contextual styling rules.
- **`revisions` (optional dictionary)**: A mapping of token indices to simulated ASR self-revisions (e.g. `{"slag": "slack"}`), modeling recognizers that emit temporary phonetic misrecognitions before settling.
