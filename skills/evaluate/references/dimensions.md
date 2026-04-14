# Review Dimensions by Document Type

Each document type has a set of evaluation dimensions. Use these as a guide — reviewers may skip, reorder, or add dimensions as needed.

---

## Plan (Architecture / Design)

For documents in `docs/plans/` describing system architecture, technical design, or migration plans.

### Dimensions

1. **Problem Definition**
   - Is the problem clearly stated with concrete evidence?
   - Are the pain points real and significant?
   - Is the scope well-bounded (goals vs. non-goals)?

2. **Solution Design**
   - Does the proposed solution address all stated problems?
   - Is the architecture clear and internally consistent?
   - Are component responsibilities well-defined?
   - Are interfaces between components explicit?

3. **Alternatives Analysis**
   - Were viable alternatives considered?
   - Is the comparison fair and thorough?
   - Is the rationale for the chosen approach convincing?
   - Are there unconsidered alternatives?

4. **Feasibility & Complexity**
   - Is the solution technically feasible with current resources?
   - Is the complexity proportional to the problem?
   - Are there simpler approaches that would suffice?
   - Are dependencies and prerequisites identified?

5. **Risk Assessment**
   - Are risks identified comprehensively?
   - Are mitigation strategies concrete and actionable?
   - Are there unidentified risks?
   - What's the worst-case scenario?

6. **Migration & Rollout**
   - Is the migration path clear and phased?
   - Are rollback strategies defined?
   - Is the timeline realistic?
   - What are the dependencies between phases?

7. **Maintainability**
   - Will this design be easy to understand for new team members?
   - Are operational concerns addressed (monitoring, debugging)?
   - Does it create tech debt? Is that debt acknowledged?

---

## PRD (Product Requirements)

For product requirement documents describing features, user stories, and acceptance criteria.

### Dimensions

1. **User Problem**
   - Is the user problem clearly articulated?
   - Is there evidence of real user need (data, feedback, research)?
   - Who are the target users? Are personas defined?

2. **Requirements Completeness**
   - Are functional requirements specific and testable?
   - Are non-functional requirements defined (performance, security, accessibility)?
   - Are edge cases and error states covered?
   - Are acceptance criteria measurable?

3. **Scope & Priority**
   - Is the scope well-defined (in-scope vs. out-of-scope)?
   - Are requirements prioritized (must-have vs. nice-to-have)?
   - Is the MVP clearly identified?

4. **User Experience**
   - Are user flows described?
   - Are interaction patterns clear?
   - Is the design consistent with existing product patterns?
   - Are accessibility concerns addressed?

5. **Technical Feasibility**
   - Are there known technical constraints?
   - Are integration points identified?
   - Are data requirements specified?

6. **Success Metrics**
   - How will success be measured?
   - Are metrics specific and time-bound?
   - Is there a baseline for comparison?

7. **Dependencies & Risks**
   - What are the external dependencies?
   - What are the risks to delivery?
   - Are there regulatory or compliance considerations?

---

## Deploy (Deployment / Release)

For deployment plans, release checklists, and infrastructure change specs.

### Dimensions

1. **Change Description**
   - Is the change clearly described?
   - What systems/services are affected?
   - What's the expected impact on users?

2. **Pre-conditions**
   - Are all prerequisites listed?
   - Are dependency versions specified?
   - Is the environment state validated?

3. **Rollout Strategy**
   - Is the rollout phased (canary, blue-green, etc.)?
   - Are health checks defined?
   - What's the go/no-go criteria at each phase?

4. **Rollback Plan**
   - Is rollback clearly documented?
   - Has rollback been tested?
   - What's the maximum acceptable rollback time?
   - Are there data implications of rollback?

5. **Monitoring & Alerting**
   - What metrics should be watched during/after deploy?
   - Are alert thresholds defined?
   - Who is on-call?

6. **Communication**
   - Are stakeholders identified and notified?
   - Is there a user-facing changelog?
   - What's the escalation path?

7. **Post-deploy Validation**
   - What smoke tests should run?
   - How long is the observation period?
   - When is the deploy considered "complete"?

---

## Design (Requirements / System Design)

For requirements design documents, system design specs, API design, data model design, etc.

### Dimensions

1. **Requirements Traceability**
   - Does each design decision trace back to a stated requirement?
   - Are there requirements without corresponding design elements?
   - Are there design elements without corresponding requirements (scope creep)?

2. **Interface Design**
   - Are APIs / interfaces clearly defined (input, output, errors)?
   - Are contracts explicit and versioned?
   - Is backward compatibility considered?
   - Are data formats and protocols specified?

3. **Data Model**
   - Is the data model complete and normalized appropriately?
   - Are relationships and constraints defined?
   - Is data lifecycle addressed (creation, update, deletion, archival)?
   - Are privacy and compliance requirements reflected in the model?

4. **Error Handling & Edge Cases**
   - Are failure modes identified and handled?
   - Are timeout, retry, and fallback strategies defined?
   - Are concurrent access / race conditions addressed?
   - Are boundary conditions documented?

5. **Security**
   - Is authentication and authorization designed?
   - Are data-at-rest and data-in-transit protections specified?
   - Are input validation rules defined?
   - Is the principle of least privilege applied?

6. **Scalability & Performance**
   - Are expected load patterns described?
   - Are bottlenecks identified and mitigated?
   - Are caching and optimization strategies specified?

7. **Testability**
   - Can each component be tested independently?
   - Are test strategies outlined (unit, integration, e2e)?
   - Are test data requirements identified?

---

## Implementation (Code / PR / Feature)

For evaluating code implementations, pull requests, or completed feature branches. The target can be a PR URL, a branch diff, or a code directory.

### Dimensions

1. **Correctness**
   - Does the implementation match the design / requirements?
   - Are all specified behaviors implemented?
   - Are edge cases handled as designed?
   - Are there logic errors or off-by-one bugs?

2. **Code Quality**
   - Is the code readable and well-structured?
   - Are naming conventions consistent?
   - Is complexity reasonable (no unnecessary abstractions, no god functions)?
   - Is there duplicated logic that should be extracted?

3. **Error Handling**
   - Are errors caught and handled appropriately?
   - Are error messages informative for debugging?
   - Are resources properly cleaned up (connections, file handles)?
   - Are failure paths tested?

4. **Testing**
   - Is test coverage adequate for the change?
   - Are tests meaningful (not just coverage padding)?
   - Are edge cases and error paths tested?
   - Do tests run reliably (no flaky tests)?

5. **Security**
   - Is user input validated and sanitized?
   - Are there injection risks (SQL, XSS, command)?
   - Are secrets properly managed (no hardcoded credentials)?
   - Are permissions checked before sensitive operations?

6. **Performance**
   - Are there N+1 query patterns or unnecessary loops?
   - Are large data sets handled efficiently?
   - Are expensive operations cached or batched?
   - Is memory usage reasonable?

7. **Integration**
   - Does this change break existing behavior?
   - Are migration / rollback steps provided?
   - Are downstream consumers considered?
   - Is documentation updated?

---

## E2E Test (End-to-End Test Plan / Suite)

For evaluating E2E test plans, test suites, or test execution reports.

### Dimensions

1. **Coverage**
   - Are all critical user journeys covered?
   - Are happy paths AND unhappy paths tested?
   - Are cross-feature interactions tested?
   - Is the coverage mapped to requirements / acceptance criteria?

2. **Test Design**
   - Are test cases independent and idempotent?
   - Are preconditions and postconditions explicit?
   - Are test data requirements defined?
   - Are tests deterministic (no random failures)?

3. **Environment & Setup**
   - Is the test environment clearly specified?
   - Are external dependency stubs / mocks defined?
   - Is test data seeding automated?
   - Can tests run in CI without manual intervention?

4. **Assertions & Validation**
   - Are assertions specific and meaningful (not just status 200)?
   - Are side effects verified (DB state, event emission, notifications)?
   - Are timing-sensitive assertions properly handled (waits, retries)?
   - Are error messages validated, not just error codes?

5. **Maintainability**
   - Are page objects / helpers used to avoid duplication?
   - Can tests be understood without reading implementation code?
   - Are tests tagged / categorized for selective execution?
   - Is cleanup reliable (no leftover test data)?

6. **Reliability**
   - Are flaky tests identified and quarantined?
   - Are retries used appropriately (not masking bugs)?
   - Are timeouts reasonable for the operations tested?
   - Is parallel execution safe?

7. **Reporting & Diagnostics**
   - Are failure messages actionable (what failed, expected vs actual)?
   - Are screenshots / logs captured on failure?
   - Is execution time tracked per test?
   - Are trends visible (regression detection)?

---

## Other (General Document)

For documents that don't fit the above categories.

### Dimensions

1. **Clarity** — Is the document well-structured and easy to follow?
2. **Completeness** — Does it cover the topic adequately?
3. **Accuracy** — Are claims supported by evidence?
4. **Actionability** — Does it lead to clear next steps?
5. **Audience** — Is it appropriate for the intended readers?
