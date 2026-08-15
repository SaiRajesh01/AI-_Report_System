# Section: Case Index / Listing

This section is DETERMINISTIC — no LLM generation needed.

Generate a structured case listing table from the deduplicated case data.

## Required columns:
- Case ID (safetyreportid)
- Reaction(s) / Adverse Event(s) (MedDRA PTs)
- Seriousness (serious / not serious)
- Seriousness Criteria (which criteria met)
- Reporting Date (receivedate)
- Country (primarysourcecountry)
- Outcome(s) (reaction outcomes)
- Reporter Type (primarysource_qualification)

## Format:
- Markdown table
- Sorted by receivedate (ascending)
- All 1,024 cases included (or first 50 with a note about truncation)

## Purpose:
A reviewer should be able to trace aggregate information back to individual cases.
