# Alert Routing Engine — Project Rules

## Context
Take-home exercise: Configurable Alert Routing Engine. 2-hour time-box. Deliverable is a Docker image tested by an automated suite. AI-native workflow is the primary evaluation criterion.

## Constraints
- Everything must run inside Docker. The evaluator runs `docker build` + `docker run` — nothing else.
- REST API is the public interface. Design endpoints to be stable; don't change them mid-build.
- No external databases unless explicitly required — prefer embedded/in-process storage.
- The automated test suite is the ground truth. When in doubt, optimize for test correctness over elegance.

## Architecture Principles
- Keep the codebase flat and easy to navigate. One file per concern, not one file per class.
- No premature abstractions. Build the simplest thing that passes the spec, then extend.
- Favor correctness over cleverness: timezone-aware scheduling, glob matching, and suppression windows are where bugs live — be explicit and test those paths.
- No backwards-compatibility shims. If a design is wrong, change it cleanly.

## Development Workflow
- Decompose the spec into discrete, independently testable pieces before writing any code.
- Build in this order: data model → routing logic → scheduling/suppression → API → Docker packaging.
- Run the server locally and hit endpoints manually before wiring up the full suite.
- Feed real errors back into the conversation — don't paper over them with silent catches.

## What Claude Should and Should Not Do
- **Do**: scaffold boilerplate, generate repetitive code, write tests for described behavior, catch edge cases in routing/scheduling logic.
- **Do not**: change the public API contract mid-session without explicit instruction.
- **Do not**: add error handling for cases that can't happen, or add abstractions beyond what the current task requires.
- **Do not**: create documentation files unless asked.

## Key Technical Areas (high-risk for bugs)
- Glob pattern matching for alert routing rules
- Timezone-aware scheduling (use a proper tz library, never roll your own offset math)
- Temporal suppression windows (start/end times, overlap detection)
- Rule priority and conflict resolution order
- Aggregation logic (grouping, dedup, windowing)

## Testing
- Write tests that hit real logic, not mocks of the thing under test.
- For routing and scheduling, use concrete, deterministic inputs — no random data.
- Each spec requirement should map to at least one test case.
