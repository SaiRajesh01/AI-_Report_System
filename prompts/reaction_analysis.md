# Section: Reaction / Adverse Event Analysis

Write the "Reaction / Adverse Event Analysis" section of a PADER report.

This section analyzes the adverse reactions reported during the reporting period.

## Required content (use ONLY the evidence provided):

1. **Overview**: State total reaction instances, unique Preferred Terms, and that analysis is at PT level (no SOC data available).

2. **Most frequently reported reactions table**: Top 20 PTs with counts and percentages of total reactions.

3. **Serious reactions**: Top serious Preferred Terms with counts.

4. **Outcome by top PT** (for top 5–10 PTs): Show how outcomes (recovered, fatal, unknown, etc.) distribute across the most common PTs.

5. **Sex distribution by top PT**: If provided in evidence, note any notable sex differences in top PTs.

6. **PT temporal trends**: If provided, mention any PTs with notable monthly variation.

## Important constraints:
- There is NO System Organ Class (SOC) column in the dataset. Do NOT infer or assign SOC categories.
- Explicitly state that SOC-level analysis was not possible with this dataset.
- All reaction counts are from the deduplicated case set.

## Formatting:
- Use Markdown tables for the PT frequency list and cross-tabulations.
- Brief interpretive text connecting the tables.

## EVIDENCE PACKET:
```json
{evidence_json}
```
