---
name: evaluate
description: "Collaborative document evaluation skill. Use when user wants to (1) evaluate/assess a document (PRD, plan, deploy spec) — /evaluate @path, (2) list evaluation targets — /evaluate list, (3) generate a structured evaluation report — /evaluate report, (4) sync reports to repo — /evaluate sync, (5) synthesize all evaluations for a target — /evaluate synthesis {slug}, (6) check evaluation status — /evaluate status {slug}. TRIGGER when: user says 'evaluate', 'assess', 'review a plan/PRD' a document, or references /evaluate."
---

# /evaluate — Collaborative Document Evaluation

When invoked, this skill manages structured, multi-reviewer evaluation of project documents (PRDs, plans, deploy specs). It tracks evaluation targets, guides evaluation conversations, generates reports, and supports publisher synthesis.

## Command Routing

Parse the user's input to determine the subcommand:

| Pattern | Action |
|---------|--------|
| `/evaluate @{path}` or `/evaluate {path}` | **Start evaluation** — go to [Start Evaluation Session](#1-start-evaluation-session) |
| `/evaluate list` | **List targets** — go to [List Evaluations](#2-list-evaluations) |
| `/evaluate report` | **Generate report** — go to [Generate Report](#3-generate-report) |
| `/evaluate sync` | **Sync to repo** — go to [Sync Evaluations](#4-sync-evaluations) |
| `/evaluate synthesis {slug}` | **Publisher synthesis** — go to [Synthesis](#5-synthesis) |
| `/evaluate status {slug}` | **Check status** — go to [Evaluation Status](#6-evaluation-status) |
| `/evaluate` (no args) | Show available commands (this table) |

---

## 1. Start Evaluation Session

**Trigger**: `/evaluate @docs/plans/xxx.md` or user expresses intent to evaluate a document.

### Phase 1 — Initialize

1. **Read the target document** in full.

2. **Identify document type** from content and path:
   - `plan` — architecture/design plans (in `docs/plans/`)
   - `prd` — product requirements documents
   - `design` — requirements design, API design, data model design
   - `implementation` — code, PR, feature branch (target can be a file path, PR URL, or branch name)
   - `e2e-test` — E2E test plans, test suites, test execution reports
   - `deploy` — deployment/release specs
   - `other` — anything else

3. **Get reviewer identity**:
   ```bash
   git config user.name && git config user.email
   ```

4. **Derive target slug** from filename: strip date prefix and extension.
   Example: `2026-04-09-three-layer-architecture.md` → `three-layer-architecture`

5. **Run init script** to create directory structure and register the target:
   ```bash
   uv run skills/evaluate/scripts/init_eval.py \
     --target "docs/plans/2026-04-09-three-layer-architecture.md" \
     --slug "three-layer-architecture" \
     --type plan \
     --reviewer-name "Allen Woods" \
     --reviewer-email "hjj.gemini@gmail.com"
   ```
   This creates:
   - `docs/evaluations/{slug}/meta.yaml` (if not exists)
   - `docs/evaluations/{slug}/reports/` directory
   - `.autoservice/evaluations/{slug}/sessions/` directory
   - Updates `docs/evaluations/_index.yaml`

6. **Create session file** at `.autoservice/evaluations/{slug}/sessions/{reviewer}-{date}.md` with header:
   ```markdown
   # Evaluation Session: {document title}
   - Target: {path}
   - Reviewer: {name} <{email}>
   - Date: {date}
   - Type: {doc_type}

   ---
   ```

### Phase 2 — Guided Evaluation

7. **Read the evaluation dimensions** for this document type:
   ```
   cat skills/evaluate/references/dimensions.md
   ```
   Select the dimension set matching the document type.

8. **Present the evaluation framework** to the user:
   - Show a brief summary of the document (title, status, goals, key sections)
   - List the evaluation dimensions with short descriptions
   - Invite the user to start with any dimension or discuss freely

9. **Guide the conversation** through each dimension:
   - Ask focused questions based on the dimension
   - Challenge assumptions, probe edge cases
   - Acknowledge strengths as well as weaknesses
   - The user may jump between dimensions or raise new topics — follow their lead

10. **Record the session** — after each substantive exchange (every 2-3 turns), append to the session file:
    ```markdown
    ## {Dimension or Topic}

    **Q**: {Your question or prompt}
    **A**: {User's response, summarized}
    **Key point**: {Extracted insight, concern, or decision}
    ```

    Use the Edit tool to append to the session file. Keep the session record concise — capture substance, not verbatim transcripts.

### Phase 3 — Wrap Up

11. When the user indicates they're done (or all dimensions are covered), summarize:
    - Dimensions covered
    - Key findings so far
    - Any dimensions skipped

12. Ask: "Ready to generate the evaluation report? (`/evaluate report`)"

---

## 2. List Evaluations

**Trigger**: `/evaluate list`

Run the list script:
```bash
uv run skills/evaluate/scripts/list_evals.py
```

Display the output as a formatted table showing all evaluation targets, their types, report counts, and statuses.

---

## 3. Generate Report

**Trigger**: `/evaluate report`

**Prerequisite**: An evaluation session must have been started in this conversation (session file exists).

1. **Read the session file** from `.autoservice/evaluations/{slug}/sessions/{reviewer}-{date}.md`

2. **Read the report template**:
   ```
   cat skills/evaluate/templates/report.md
   ```

3. **Extract and organize** from the session:
   - **Overall assessment** — 1-2 paragraph summary
   - **Checklist items** — key points confirmed or missing (use `- [x]` / `- [ ]`)
   - **Questions & concerns** — numbered, with context
   - **Risk identification** — table format with severity and mitigation suggestions
   - **Improvement suggestions** — specific, actionable items
   - **Session highlights** — notable discussion excerpts as blockquotes
   - **Overall score** — X/5 (ask user to confirm)

4. **Write the report** to `docs/evaluations/{slug}/reports/{reviewer}-{date}.md` using the template structure with YAML frontmatter.

5. **Update meta.yaml** — increment review count, update last_review_date.

6. **Show the report** to the user for confirmation. Ask if they want to edit anything before finalizing.

---

## 4. Sync Evaluations

**Trigger**: `/evaluate sync`

Commit and push all evaluation files:

1. Stage evaluation files:
   ```bash
   git add docs/evaluations/
   ```

2. Generate a commit message:
   ```
   evaluate({slug}): add evaluation by {reviewer}
   ```

3. Invoke the `/git-sync` skill to handle the commit + push flow with user confirmation.

If `/git-sync` is not available, fall back to manual git commands with user confirmation at each step.

---

## 5. Synthesis

**Trigger**: `/evaluate synthesis {slug}`

This is for the **document publisher** to consolidate all evaluations.

1. **Read all evaluation reports** in `docs/evaluations/{slug}/reports/*.md`

2. **Read the synthesis template**:
   ```
   cat skills/evaluate/templates/synthesis.md
   ```

3. **Cross-analyze** the evaluations:
   - **Consensus** — points all reviewers agree on
   - **Divergence** — points where reviewers disagree (with each side's reasoning)
   - **Question consolidation** — deduplicate questions, note who raised each
   - **Risk matrix** — merge all identified risks, sort by severity
   - **Action items** — extract concrete TODOs from all suggestions

4. **Get publisher identity**:
   ```bash
   git config user.name && git config user.email
   ```

5. **Write synthesis** to `docs/evaluations/{slug}/synthesis.md` with YAML frontmatter.

6. **Present the synthesis** to the publisher. Ask if they want to:
   - Add decision records (what they decided based on feedback)
   - Update the original document based on the synthesis
   - Sync the synthesis to the repo (`/evaluate sync`)

---

## 6. Evaluation Status

**Trigger**: `/evaluate status {slug}`

1. **Read meta.yaml** from `docs/evaluations/{slug}/meta.yaml`
2. **List all report files** in `docs/evaluations/{slug}/reports/`
3. **Check for synthesis** — does `synthesis.md` exist?

Display:
- Target document path and type
- Number of evaluations completed
- Reviewer names and dates
- Whether synthesis has been done
- Last activity date

---

## Session State Management

This skill maintains state across a conversation through:
- The **session file** (`.autoservice/evaluations/{slug}/sessions/{reviewer}-{date}.md`) — written incrementally during the evaluation
- The **target slug** and **reviewer identity** — established at session start

When the user returns to evaluation-related commands in the same conversation, use the established session context. If no session exists and the user runs `/evaluate report`, prompt them to start an evaluation first.

---

## Important Guidelines

- **Be a thoughtful evaluator, not a rubber stamp.** Ask probing questions. Challenge vague statements. Identify what's missing, not just what's present.
- **Respect the user's expertise.** They may know more about the domain. Your role is to structure their thinking, not override it.
- **Keep session records concise.** Capture key points and decisions, not every word. The report is what gets shared.
- **Never modify the target document** during an evaluation session. The evaluation is about the document as-is.
- **Dimension coverage is a guide, not a mandate.** If the user wants to focus on specific areas, follow their lead.
- **Score is subjective.** Always ask the user to confirm or adjust the overall score.
