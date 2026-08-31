# check_suite.ps1
$DB = "taskdb_test"
$LogFile = Join-Path $PSScriptRoot "check_suite_output.txt"
Remove-Item -Path $LogFile -ErrorAction SilentlyContinue

function Log($text) {
    Write-Host $text
    Add-Content -Path $LogFile -Value $text -Encoding ascii
}

function Section($title) {
    Log ""
    Log "=== $title ==="
}

function Invoke-Logged($cmd) {
    # Runs a command, streams its output to console AND the log file, preserves $LASTEXITCODE.
    # -Encoding ascii here matches Log()'s encoding so the file doesn't end up
    # with mixed UTF-16/ASCII content (which shows up as null bytes between chars).
    & $cmd *>&1 | Tee-Object -FilePath $LogFile -Append -Encoding ascii
}

Section "1/6 - Baseline run (should be all green)"
Invoke-Logged { python -m pytest -q }
if ($LASTEXITCODE -ne 0) {
    Log "FAIL: Baseline is already failing. Stop here and fix that first - the checks below assume a clean baseline."
    exit 1
}
Log "OK - baseline passed. Look for: no failures, no errors, count of tests matches what you expect (139 currently)."

Section "2/6 - Mutation check: make the suite prove it can fail"
Log "Now go edit the code (e.g. flip 'other_admins is None' to 'other_admins is not None' in users.py)."
Read-Host "Press Enter once you've made the change and saved it"
Invoke-Logged { python -m pytest -q }
if ($LASTEXITCODE -eq 0) {
    Log "FAIL: Nothing failed. That's bad - it means no test exercises this code path. Investigate before trusting the suite."
} else {
    Log "OK - something failed. Look for: the specific test(s) tied to the behavior you broke (not everything, not unrelated files)."
    Log "   e.g. breaking a last-admin guard should fail last-admin tests, not comment or auth tests."
}
Read-Host "Now revert your change, save, and press Enter to continue"
Invoke-Logged { python -m pytest -q -x }
if ($LASTEXITCODE -ne 0) {
    Log "FAIL: Suite still failing after revert - you may not have fully undone the change. Fix before continuing."
    exit 1
}
Log "OK - back to green after revert."

Section "3/6 - Isolation check: DB should be empty after a run"
Invoke-Logged { psql -U postgres -d $DB -c "\dt" }
Log "Look for: 'Did not find any relations.' - tables are dropped at teardown. If you see leftover tables, isolation is broken."

Section "4/6 - Repeatability: run twice back-to-back"
Invoke-Logged { python -m pytest -q }
$first = $LASTEXITCODE
if ($first -eq 0) { Invoke-Logged { python -m pytest -q } }
if ($LASTEXITCODE -ne 0) {
    Log "FAIL: Second run failed. Look for: 'duplicate name/email' style errors - that means state is leaking between runs."
} else {
    Log "OK - both runs passed with identical results."
}

Section "5/6 - Order independence"
$hasRandomly = $false
python -c "import pytest_randomly" 2>$null
if ($LASTEXITCODE -eq 0) { $hasRandomly = $true }
if ($hasRandomly) {
    Invoke-Logged { python -m pytest -q -p randomly }
    Log "Look for: same pass count as the baseline. A test that only passes in one order depends on another test's leftovers."
} else {
    Log "Skipped - pip install pytest-randomly to enable this check."
}

Section "6/6 - Flakiness: run 3x, watch for inconsistent results"
for ($i = 1; $i -le 3; $i++) {
    Log "--- run $i ---"
    Invoke-Logged { python -m pytest -q }
    Log "exit code: $LASTEXITCODE"
}
Log "Look for: identical pass/fail outcome every run. Any test that flips between runs needs fixing before CI."

Log ""
Log "=== Done. Summary of what looks right: ==="
Log "  1. Baseline: all green"
Log "  2. Mutation: specific, relevant test(s) failed - not zero, not everything"
Log "  3. Isolation: no tables left in $DB after a run"
Log "  4/5/6. Repeat/order/flake runs: identical results every time"

Write-Host ""
Write-Host "Full output written to: $LogFile"