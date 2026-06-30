# S5 Advisory Notes

## Changed

- `agent-front/src/features/contract/tender-review/model.ts`: added `buildIssueList()` and `getAdvisoryLabel()`, deriving seven advisory issue categories from existing `extracted_data`.
- `agent-front/src/features/contract/tender-review/types.ts`: added `IssueCategory`, `IssueStatus`, `IssueItem`, and `TenderReviewMockData.issueList`.
- `agent-front/src/features/contract/tender-review/components/analysis-workbench-view.tsx`: replaced score summary/ranking/verdict presentation with risk counts and grouped issue list.
- `agent-front/src/features/contract/tender-review/components/report-view.tsx`: replaced verdict/recommendation conclusion with issue-list summary and weakened scoring context to reference-only structure.
- `agent-front/src/features/contract/tender-review/components/dashboard-view.tsx`, `history-view.tsx`, `scoring-detail-table.tsx`: removed expert-side score/rank leakage from surrounding tender-review surfaces.
- `agent-front/src/features/contract/tender-review/model.test.ts`: added seven-category issue-list coverage and the `confirmed:false/null -> pending_verification` guard.
- `agent-front/package.json`, `agent-front/bun.lock`: added `react-day-picker`, required by existing `src/components/ui/calendar.tsx` for the build gate.

## Gates

- `cd agent-front && bun test src/features/contract/tender-review/model.test.ts` -> 14 pass, 0 fail.
- `cd agent-front && bun run lint` -> pass.
- `cd agent-front && bun run build` -> pass; Vite emitted only existing chunk-size warnings.

## Guardrails

- `confirmed:false` / `confirmed:null` disqualification hits, manual eligibility checks, and unclear/unreadable wording are classified as `pending_verification`.
- Expert-facing tender-review views no longer render earned totals, explicit bidder totals, rank badges, verdict badges, or first-candidate recommendation wording.

## Notes

- Backend contracts, S4 files, schemas, prompts, `.ai_state/_index.md`, and roadmap items were not touched.
- `react-day-picker` dependency was added only because the required frontend build was failing on the pre-existing calendar import.
