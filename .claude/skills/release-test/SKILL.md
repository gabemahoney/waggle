# /release-test — Waggle MCP Tool Integration Tests

Run all waggle MCP tool integration tests from the testplans hive. Executes each test in order, stops on first failure, and prints `WAGGLE CI PHASE 2 PASSED` if all tests pass.

## Instructions

Execute the following steps using bees MCP tools and waggle MCP tools. Do NOT fix, retry, or modify anything on failure — one failure means stop immediately.

### Step 1 — Fetch all test tickets

Use the bees MCP tool to fetch all bee tickets from the testplans hive:

```
mcp__bees__execute_freeform_query(query_yaml="- [type=bee]")
```

This returns a list of ticket IDs. Then retrieve each ticket's full details using `mcp__bees__show_ticket(ticket_ids=[...])`.

Count the total number of tickets (TOTAL).

### Step 2 — Execute each test in order

For each ticket (N from 1 to TOTAL), in the order returned by bees:

1. **Read** the ticket body — it contains: Setup, Steps, Expected Response, Pass Criteria, Fail Criteria, Teardown

2. **Execute Setup** — run any bash commands or MCP calls specified in the Setup section

3. **Execute each Step** — call the waggle MCP tool specified in the Steps section with the exact parameters listed

4. **Evaluate** — compare the actual response against the Pass Criteria

5. **Execute Teardown** — always run teardown regardless of pass or fail

6. **Print result**:
   - On pass: `[N/TOTAL] PASS: <title>`
   - On fail: `[N/TOTAL] FAIL: <title> — <error detail>`

### Step 3 — Stop on first failure

If any test fails (Pass Criteria not met, or any exception):
- Print the `[N/TOTAL] FAIL: <title> — <error detail>` line
- Stop immediately. Do not run any more tests.
- Do not attempt to fix or retry anything.

### Step 4 — Success signal

After ALL tests pass without any failure, print:
```
WAGGLE CI PHASE 2 PASSED
```

## Important Rules

- **Never fix, retry, or modify** anything when a test fails — just report and stop
- **Always run Teardown** for a test even if the test fails
- **Stop on first failure** — do not continue to the next test
- **Exact output format**: `[N/TOTAL] PASS: <title>` or `[N/TOTAL] FAIL: <title> — <error>`
- The final line on full success must be exactly `WAGGLE CI PHASE 2 PASSED`
