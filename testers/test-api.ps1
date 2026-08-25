#Requires -Version 5.1
<#
.SYNOPSIS
    End-to-end test suite for the Team Task Management API.

.DESCRIPTION
    Exercises every endpoint (auth, users, projects, tasks, comments, admin) and the
    business rules layered on top of them (role hierarchy, project-name uniqueness,
    per-project task-title uniqueness, "last admin" protection, etc.).

    PREREQUISITES
      - The API must already be running (default: http://localhost:8000).
      - No site-admin account is required or created by this script: self-registration
        always yields global_role = "member" (the site-admin role can only be granted
        by an existing admin, or via a one-time bootstrap script run directly against
        the DB). Every admin-only endpoint is therefore tested for its 403 response,
        which is the only behavior a script without admin credentials can verify.
      - Safe to re-run against a non-empty database: every email and project/task name
        used here is stamped with the current timestamp + a random suffix, so repeat
        runs never collide with leftover data from a previous run.

.PARAMETER BaseUrl
    Root URL of the running API. Defaults to http://localhost:8000.

.PARAMETER AdminEmail
    Email of an already-bootstrapped site-admin account. Optional -- when
    supplied together with -AdminPassword, an extra phase runs that exercises
    the actual 200-path behavior behind every admin-only endpoint (resolving
    a real security alert, promoting/demoting a global role, and confirming
    the site-admin membership bypass on GET/PATCH/list for a project the
    admin never joined). Omit both and the script still covers every
    admin route's 403 rejection, just not the success path behind it.

.PARAMETER AdminPassword
    Password for -AdminEmail. See above.

.EXAMPLE
    ./test_api.ps1
    ./test_api.ps1 -BaseUrl "http://localhost:8080"
    ./test_api.ps1 -AdminEmail "admin@yourcompany.com" -AdminPassword "correct-horse-battery-staple"
#>

param(
    [string]$BaseUrl       = "http://localhost:8000",
    [string]$AdminEmail    = "",
    [string]$AdminPassword = ""
)

# Admin-only success-path tests (real role changes, real alert resolution,
# site-admin membership bypass) only run when credentials for an already-
# bootstrapped site admin are supplied. Without them we still cover every
# admin route's 403 rejection, just not the 200 path behind it.
$RunAdminTests = -not [string]::IsNullOrWhiteSpace($AdminEmail) -and -not [string]::IsNullOrWhiteSpace($AdminPassword)

# ---------------------------------------------------------------------------
# Global test-run state
# ---------------------------------------------------------------------------
$script:Results   = [System.Collections.Generic.List[object]]::new()
$script:TestCount = 0

# A short, collision-proof tag appended to every generated email/name so
# reruns never collide with data left behind by a previous run.
$script:RunTag = "{0}{1}" -f (Get-Date -Format "yyyyMMddHHmmssfff"), (Get-Random -Maximum 9999)

function New-TestEmail {
    param([string]$Prefix)
    # IMPORTANT: avoid RFC 6761 special-use domains (.test, .example, .invalid,
    # .localhost) -- email_validator (used by Pydantic's EmailStr) rejects
    # those outright at validation time, before any DNS/deliverability check.
    # ".dev" is a real, unreserved gTLD, so it passes syntax validation fine.
    return "$Prefix.$($script:RunTag).$(Get-Random -Maximum 9999)@apiqa.dev"
}

function New-TestName {
    param([string]$Prefix)
    return "$Prefix $($script:RunTag) $(Get-Random -Maximum 9999)"
}

function Get-AuthHeader {
    param([string]$Token)
    return @{ Authorization = "Bearer $Token" }
}

# ---------------------------------------------------------------------------
# Core test runner.
#
# Wraps Invoke-WebRequest so we always get a real HTTP status code back,
# whether the call succeeds or fails (Invoke-WebRequest throws on 4xx/5xx,
# so the failure path is handled in the catch block rather than treated as
# a script-ending error). Records a pass/fail row for every call and prints
# progress immediately, one line per test.
# ---------------------------------------------------------------------------
function Invoke-ApiTest {
    param(
        [Parameter(Mandatory)] [string]   $Name,
        [Parameter(Mandatory)] [string]   $Method,
        [Parameter(Mandatory)] [string]   $Endpoint,          # path + querystring, no host
        [Parameter(Mandatory)] [int]      $ExpectedStatus,
        [hashtable]      $Headers    = @{},
        $Body                        = $null,                 # hashtable -> JSON, or raw string for form-encoded
        [string]         $ContentType = "application/json",
        [scriptblock]    $Validate   = $null                   # receives $parsedResponse, should throw on failure
    )

    # Frame 0 is this function; frame 1 is whoever called it. Using the call
    # stack (rather than $MyInvocation) makes it unambiguous that this is the
    # line number of the CALL SITE in the main script, not inside this helper.
    $callLine = (Get-PSCallStack)[1].ScriptLineNumber

    $script:TestCount++
    $uri = "$BaseUrl$Endpoint"

    $actualStatus    = -1
    $parsedResponse  = $null
    $detailMessage   = ""

    try {
        $webParams = @{
            Uri             = $uri
            Method          = $Method
            Headers         = $Headers
            ErrorAction     = 'Stop'
            UseBasicParsing = $true   # avoids a Windows PowerShell 5.1 dependency on IE's parsing engine; ignored (already default) on PS7+
        }
        if ($null -ne $Body) {
            if ($ContentType -eq "application/x-www-form-urlencoded") {
                $webParams["Body"]        = $Body
                $webParams["ContentType"] = $ContentType
            } else {
                $webParams["Body"]        = ($Body | ConvertTo-Json -Depth 10)
                $webParams["ContentType"] = $ContentType
            }
        }

        $response     = Invoke-WebRequest @webParams
        $actualStatus = [int]$response.StatusCode

        if ($response.Content) {
            try { $parsedResponse = $response.Content | ConvertFrom-Json }
            catch { $parsedResponse = $response.Content }
        }
    }
    catch {
        # Invoke-WebRequest throws for non-2xx responses AND for connection
        # failures. Distinguish the two: a real HTTP error carries a response
        # object (with the status code we actually want to assert against);
        # a connection failure does not, and is always a genuine test failure.
        if ($_.Exception.Response) {
            $actualStatus = [int]$_.Exception.Response.StatusCode
            $rawContent   = $_.ErrorDetails.Message
            if ($rawContent) {
                try { $parsedResponse = $rawContent | ConvertFrom-Json }
                catch { $parsedResponse = $rawContent }
            }
        } else {
            $detailMessage = "Connection error: $($_.Exception.Message)"
        }
    }

    $statusOk = ($actualStatus -eq $ExpectedStatus)

    # Only run the optional body-level validation when the status already
    # matched what we expected -- a wrong status makes body checks moot.
    $validationOk = $true
    if ($statusOk -and $Validate) {
        try {
            & $Validate $parsedResponse
        } catch {
            $validationOk = $false
            $detailMessage = "Validation failed: $($_.Exception.Message)"
        }
    }

    $passed = $statusOk -and $validationOk

    if (-not $passed -and -not $detailMessage) {
        if ($parsedResponse -is [PSCustomObject] -and $parsedResponse.detail) {
            $detailMessage = "$($parsedResponse.detail)"
        } elseif ($parsedResponse) {
            $detailMessage = "$($parsedResponse)"
        }
    }

    $result = [PSCustomObject]@{
        TestName       = $Name
        Line           = $callLine
        Endpoint       = "$Method $Endpoint"
        ExpectedStatus = $ExpectedStatus
        ActualStatus   = $actualStatus
        Passed         = $passed
        Detail         = $detailMessage
    }
    $script:Results.Add($result)

    if ($passed) {
        Write-Host "[PASS] " -ForegroundColor Green -NoNewline
        Write-Host "$Name  ($Method $Endpoint -> $actualStatus)"
    } else {
        Write-Host "[FAIL] " -ForegroundColor Red -NoNewline
        Write-Host "$Name  (line $callLine, $Method $Endpoint -> expected $ExpectedStatus, got $actualStatus)" -ForegroundColor Red
        if ($detailMessage) { Write-Host "        $detailMessage" -ForegroundColor DarkYellow }
    }

    return $parsedResponse
}

Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host " Team Task Management API - End-to-End Test Suite"                    -ForegroundColor Cyan
Write-Host " Target: $BaseUrl"                                                    -ForegroundColor Cyan
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host ""

# ===========================================================================
# PHASE 1 - Registration & Auth
# ===========================================================================
Write-Host "--- Phase 1: Registration & Auth ---" -ForegroundColor Magenta

$aliceEmail = New-TestEmail "alice"
$bobEmail   = New-TestEmail "bob"
$carolEmail = New-TestEmail "carol"
$daveEmail  = New-TestEmail "dave"
$password   = "P@ssw0rd123!"

Invoke-ApiTest -Name "Register Alice" -Method POST -Endpoint "/auth/register" -ExpectedStatus 201 `
    -Body @{ name = "Alice Admin"; email = $aliceEmail; password = $password } `
    -Validate { param($r) if ($r.global_role -ne "member") { throw "expected global_role=member, got $($r.global_role)" } }

Invoke-ApiTest -Name "Duplicate registration is rejected" -Method POST -Endpoint "/auth/register" -ExpectedStatus 400 `
    -Body @{ name = "Alice Duplicate"; email = $aliceEmail; password = $password }

Invoke-ApiTest -Name "Register Bob" -Method POST -Endpoint "/auth/register" -ExpectedStatus 201 `
    -Body @{ name = "Bob Contributor"; email = $bobEmail; password = $password }

Invoke-ApiTest -Name "Register Carol" -Method POST -Endpoint "/auth/register" -ExpectedStatus 201 `
    -Body @{ name = "Carol Viewer"; email = $carolEmail; password = $password }

Invoke-ApiTest -Name "Register Dave (never joins a project)" -Method POST -Endpoint "/auth/register" -ExpectedStatus 201 `
    -Body @{ name = "Dave Outsider"; email = $daveEmail; password = $password }

function Get-LoginToken {
    param([string]$Email, [string]$Name, [string]$Password = $password)
    $formBody = "username=$([uri]::EscapeDataString($Email))&password=$([uri]::EscapeDataString($Password))"
    $resp = Invoke-ApiTest -Name "Login $Name" -Method POST -Endpoint "/auth/login" -ExpectedStatus 200 `
        -Body $formBody -ContentType "application/x-www-form-urlencoded" `
        -Validate { param($r) if (-not $r.access_token) { throw "no access_token in response" } }
    return $resp.access_token
}

$aliceToken = Get-LoginToken -Email $aliceEmail -Name "Alice"
$bobToken   = Get-LoginToken -Email $bobEmail   -Name "Bob"
$carolToken = Get-LoginToken -Email $carolEmail -Name "Carol"
$daveToken  = Get-LoginToken -Email $daveEmail  -Name "Dave"

$aliceAuth = Get-AuthHeader $aliceToken
$bobAuth   = Get-AuthHeader $bobToken
$carolAuth = Get-AuthHeader $carolToken
$daveAuth  = Get-AuthHeader $daveToken

Invoke-ApiTest -Name "GET current profile (Alice)" -Method GET -Endpoint "/users/me" -ExpectedStatus 200 `
    -Headers $aliceAuth `
    -Validate { param($r) if ($r.email -ne $aliceEmail) { throw "email mismatch" } }

$newAliceName = New-TestName "Alice Renamed"
Invoke-ApiTest -Name "PATCH own profile updates name (Alice)" -Method PATCH -Endpoint "/users/me" -ExpectedStatus 200 `
    -Headers $aliceAuth -Body @{ name = $newAliceName } `
    -Validate { param($r) if ($r.name -ne $newAliceName) { throw "name was not updated" } }

# NOTE: /users/lookup now requires the caller to hold manager/admin rank in
# at least one project (or be a site admin). Alice doesn't have that yet at
# this point -- she hasn't created a project. Those lookups (and the
# role-change test below, which needs a real $bobId) have moved to Phase 3,
# right after Alice creates project A and becomes its admin.

# ===========================================================================
# PHASE 2 - Projects & project-name uniqueness
# ===========================================================================
Write-Host ""
Write-Host "--- Phase 2: Projects & Name Uniqueness ---" -ForegroundColor Magenta

$projectAName = New-TestName "Website Relaunch"
$projectBName = New-TestName "Mobile App"

$projectA = Invoke-ApiTest -Name "Create project A (Alice)" -Method POST -Endpoint "/projects/" -ExpectedStatus 201 `
    -Headers $aliceAuth -Body @{ name = $projectAName; description = "Marketing site rebuild" }
$projectAId = $projectA.id

Invoke-ApiTest -Name "Project name is globally unique -- second owner blocked" -Method POST -Endpoint "/projects/" -ExpectedStatus 400 `
    -Headers $bobAuth -Body @{ name = $projectAName; description = "Bob trying to steal the name" }

$projectB = Invoke-ApiTest -Name "Create project B (Bob, distinct name)" -Method POST -Endpoint "/projects/" -ExpectedStatus 201 `
    -Headers $bobAuth -Body @{ name = $projectBName; description = "Native app work" }
$projectBId = $projectB.id

Invoke-ApiTest -Name "List projects filtered by status" -Method GET -Endpoint "/projects/?status=active&limit=50&offset=0" -ExpectedStatus 200 `
    -Headers $aliceAuth

Invoke-ApiTest -Name "Get project A by id" -Method GET -Endpoint "/projects/$projectAId" -ExpectedStatus 200 `
    -Headers $aliceAuth -Validate { param($r) if ($r.name -ne $projectAName) { throw "unexpected project name" } }

Invoke-ApiTest -Name "Renaming project to its own current name succeeds" -Method PATCH -Endpoint "/projects/$projectAId" -ExpectedStatus 200 `
    -Headers $aliceAuth -Body @{ name = $projectAName }

Invoke-ApiTest -Name "Renaming project to a name already in use is rejected" -Method PATCH -Endpoint "/projects/$projectAId" -ExpectedStatus 400 `
    -Headers $aliceAuth -Body @{ name = $projectBName }

# ===========================================================================
# PHASE 3 - Project membership
# ===========================================================================
Write-Host ""
Write-Host "--- Phase 3: Project Membership ---" -ForegroundColor Magenta

# Alice became project A's admin the moment she created it (Phase 2), so she
# now has manager-tier standing on at least one project -- /users/lookup will
# 200 for her. This must happen here, not in Phase 1, or it 403s.
$bobLookup = Invoke-ApiTest -Name "Look up Bob by email" -Method GET -Endpoint "/users/lookup?email=$([uri]::EscapeDataString($bobEmail))" -ExpectedStatus 200 `
    -Headers $aliceAuth
$bobId = $bobLookup.id

$carolLookup = Invoke-ApiTest -Name "Look up Carol by email" -Method GET -Endpoint "/users/lookup?email=$([uri]::EscapeDataString($carolEmail))" -ExpectedStatus 200 `
    -Headers $aliceAuth
$carolId = $carolLookup.id

$daveLookup = Invoke-ApiTest -Name "Look up Dave by email" -Method GET -Endpoint "/users/lookup?email=$([uri]::EscapeDataString($daveEmail))" -ExpectedStatus 200 `
    -Headers $aliceAuth
$daveId = $daveLookup.id

Invoke-ApiTest -Name "Non-site-admin cannot change global roles" -Method PATCH -Endpoint "/users/$bobId/role" -ExpectedStatus 403 `
    -Headers $bobAuth -Body @{ global_role = "admin" }

Invoke-ApiTest -Name "Add Bob to project A as contributor" -Method POST -Endpoint "/projects/$projectAId/members" -ExpectedStatus 201 `
    -Headers $aliceAuth -Body @{ user_id = $bobId; project_role = "contributor" }

Invoke-ApiTest -Name "Add Carol to project A as viewer" -Method POST -Endpoint "/projects/$projectAId/members" -ExpectedStatus 201 `
    -Headers $aliceAuth -Body @{ user_id = $carolId; project_role = "viewer" }

Invoke-ApiTest -Name "Adding an existing member again is rejected" -Method POST -Endpoint "/projects/$projectAId/members" -ExpectedStatus 400 `
    -Headers $aliceAuth -Body @{ user_id = $bobId; project_role = "contributor" }

Invoke-ApiTest -Name "List project A members shows all three" -Method GET -Endpoint "/projects/$projectAId/members" -ExpectedStatus 200 `
    -Headers $aliceAuth -Validate { param($r) if (@($r).Count -ne 3) { throw "expected 3 members, got $(@($r).Count)" } }

# ===========================================================================
# PHASE 4 - Tasks & per-project title uniqueness
# ===========================================================================
Write-Host ""
Write-Host "--- Phase 4: Tasks & Title Uniqueness ---" -ForegroundColor Magenta

$sharedTaskTitle = New-TestName "Design Homepage"
$secondTaskTitle = New-TestName "Fix Login Bug"
$tomorrow = (Get-Date).AddDays(1).ToString("yyyy-MM-dd")

$task1 = Invoke-ApiTest -Name "Create task 1 in project A" -Method POST -Endpoint "/tasks/" -ExpectedStatus 201 `
    -Headers $aliceAuth -Body @{ project_id = $projectAId; title = $sharedTaskTitle; priority = "medium" }
$task1Id = $task1.id

$taskInB = Invoke-ApiTest -Name "Same task title is allowed in a DIFFERENT project" -Method POST -Endpoint "/tasks/" -ExpectedStatus 201 `
    -Headers $bobAuth -Body @{ project_id = $projectBId; title = $sharedTaskTitle; priority = "low" }
$taskInBId = $taskInB.id

Invoke-ApiTest -Name "Duplicate task title WITHIN same project is rejected" -Method POST -Endpoint "/tasks/" -ExpectedStatus 400 `
    -Headers $aliceAuth -Body @{ project_id = $projectAId; title = $sharedTaskTitle }

$task2 = Invoke-ApiTest -Name "Create task 2 in project A" -Method POST -Endpoint "/tasks/" -ExpectedStatus 201 `
    -Headers $aliceAuth -Body @{ project_id = $projectAId; title = $secondTaskTitle; priority = "high"; due_date = $tomorrow }
$task2Id = $task2.id

Invoke-ApiTest -Name "List tasks for project A" -Method GET -Endpoint "/tasks/project/$projectAId" -ExpectedStatus 200 `
    -Headers $aliceAuth -Validate { param($r) if (@($r).Count -lt 2) { throw "expected at least 2 tasks" } }

Invoke-ApiTest -Name "Get task 1 by id" -Method GET -Endpoint "/tasks/$task1Id" -ExpectedStatus 200 -Headers $aliceAuth

Invoke-ApiTest -Name "Viewer cannot create a task (needs contributor+)" -Method POST -Endpoint "/tasks/" -ExpectedStatus 403 `
    -Headers $carolAuth -Body @{ project_id = $projectAId; title = "Should never exist" }

Invoke-ApiTest -Name "Assign Bob to task 1" -Method POST -Endpoint "/tasks/$task1Id/assign?user_id=$bobId" -ExpectedStatus 201 `
    -Headers $aliceAuth

Invoke-ApiTest -Name "Cannot assign a non-project-member (Dave) to a task" -Method POST -Endpoint "/tasks/$task1Id/assign?user_id=$daveId" -ExpectedStatus 400 `
    -Headers $aliceAuth

Invoke-ApiTest -Name "Viewer cannot change task status (needs contributor+)" -Method PATCH -Endpoint "/tasks/$task1Id" -ExpectedStatus 403 `
    -Headers $carolAuth -Body @{ status = "in_progress" }

Invoke-ApiTest -Name "Contributor CAN change task status" -Method PATCH -Endpoint "/tasks/$task1Id" -ExpectedStatus 200 `
    -Headers $bobAuth -Body @{ status = "in_progress" } `
    -Validate { param($r) if ($r.status -ne "in_progress") { throw "status did not update" } }

Invoke-ApiTest -Name "Contributor CANNOT rename a task (needs manager+)" -Method PATCH -Endpoint "/tasks/$task1Id" -ExpectedStatus 403 `
    -Headers $bobAuth -Body @{ title = "Bob should not be able to set this" }

Invoke-ApiTest -Name "Manager+ renaming task to a title already used in-project is rejected" -Method PATCH -Endpoint "/tasks/$task1Id" -ExpectedStatus 400 `
    -Headers $aliceAuth -Body @{ title = $secondTaskTitle }

Invoke-ApiTest -Name "Renaming task to its own current title succeeds" -Method PATCH -Endpoint "/tasks/$task1Id" -ExpectedStatus 200 `
    -Headers $aliceAuth -Body @{ title = $sharedTaskTitle }

Invoke-ApiTest -Name "Task status-history reflects the transition" -Method GET -Endpoint "/tasks/$task1Id/history" -ExpectedStatus 200 `
    -Headers $aliceAuth -Validate { param($r) if (@($r).Count -lt 1) { throw "expected at least one history entry" } }

Invoke-ApiTest -Name "Bob sees task 1 under his assigned tasks" -Method GET -Endpoint "/tasks/assigned/me" -ExpectedStatus 200 `
    -Headers $bobAuth -Validate { param($r) if (-not (@($r) | Where-Object { $_.id -eq $task1Id })) { throw "task 1 missing from assigned list" } }

# ===========================================================================
# PHASE 5 - Comments (including a threaded reply)
# ===========================================================================
Write-Host ""
Write-Host "--- Phase 5: Comments ---" -ForegroundColor Magenta

$comment1 = Invoke-ApiTest -Name "Bob comments on task 1" -Method POST -Endpoint "/comments/" -ExpectedStatus 201 `
    -Headers $bobAuth -Body @{ task_id = $task1Id; content = "Looks good so far." }
$comment1Id = $comment1.id

$reply1 = Invoke-ApiTest -Name "Alice replies to Bob's comment (threaded)" -Method POST -Endpoint "/comments/" -ExpectedStatus 201 `
    -Headers $aliceAuth -Body @{ task_id = $task1Id; content = "Agreed, ship it."; parent_comment_id = $comment1Id }
$reply1Id = $reply1.id

Invoke-ApiTest -Name "Viewer cannot post a comment (needs contributor+)" -Method POST -Endpoint "/comments/" -ExpectedStatus 403 `
    -Headers $carolAuth -Body @{ task_id = $task1Id; content = "I should not be allowed to post this." }

Invoke-ApiTest -Name "Comment tree for task 1 contains the threaded reply" -Method GET -Endpoint "/comments/task/$task1Id" -ExpectedStatus 200 `
    -Headers $aliceAuth `
    -Validate {
        param($r)
        $root = @($r) | Where-Object { $_.id -eq $comment1Id }
        if (-not $root) { throw "root comment missing" }
        if (-not (@($root[0].replies) | Where-Object { $_.id -eq $reply1Id })) { throw "reply not nested under its parent" }
    }

Invoke-ApiTest -Name "Non-author cannot edit someone else's comment" -Method PATCH -Endpoint "/comments/$comment1Id" -ExpectedStatus 403 `
    -Headers $carolAuth -Body @{ content = "Hijacked!" }

Invoke-ApiTest -Name "Author can edit their own comment" -Method PATCH -Endpoint "/comments/$comment1Id" -ExpectedStatus 200 `
    -Headers $bobAuth -Body @{ content = "Looks good so far. (edited)" }

Invoke-ApiTest -Name "Author can delete their own reply" -Method DELETE -Endpoint "/comments/$reply1Id" -ExpectedStatus 204 `
    -Headers $aliceAuth

# ===========================================================================
# PHASE 6 - Stats & admin gating
# ===========================================================================
Write-Host ""
Write-Host "--- Phase 6: Stats & Admin Gating ---" -ForegroundColor Magenta

Invoke-ApiTest -Name "Project A stats reflect its tasks" -Method GET -Endpoint "/projects/$projectAId/stats" -ExpectedStatus 200 `
    -Headers $aliceAuth -Validate { param($r) if ($r.total_tasks -lt 2) { throw "expected at least 2 tasks in stats" } }

Invoke-ApiTest -Name "Non-site-admin blocked from security alerts (list)" -Method GET -Endpoint "/admin/alerts?include_resolved=false" -ExpectedStatus 403 `
    -Headers $aliceAuth

Invoke-ApiTest -Name "Non-site-admin blocked from resolving alerts" -Method PATCH -Endpoint "/admin/alerts/nonexistent-id/resolve" -ExpectedStatus 403 `
    -Headers $aliceAuth

Invoke-ApiTest -Name "Non-site-admin blocked from transferring admin rights" -Method POST -Endpoint "/admin/transfer-admin" -ExpectedStatus 403 `
    -Headers $daveAuth -Body @{ new_admin_user_id = $carolId }

# ===========================================================================
# PHASE 6.5 - Admin-privileged success paths (only with -AdminEmail/-AdminPassword)
# ===========================================================================
if ($RunAdminTests) {
    Write-Host ""
    Write-Host "--- Phase 6.5: Admin-Privileged Actions ---" -ForegroundColor Magenta

    $adminToken = Get-LoginToken -Email $AdminEmail -Name "Admin (bootstrap)" -Password $AdminPassword
    $adminAuth  = Get-AuthHeader $adminToken

    # Phase 3's "Non-site-admin cannot change global roles" test (Bob trying
    # to set his own role) already wrote a real, resolvable SecurityAlert --
    # reuse it instead of needing to manufacture one here.
    $alertsResp = Invoke-ApiTest -Name "Site admin can list unresolved security alerts" -Method GET -Endpoint "/admin/alerts?include_resolved=false" -ExpectedStatus 200 `
        -Headers $adminAuth
    $bobAlert = @($alertsResp) | Where-Object { $_.target_user_id -eq $bobId -and $_.alert_type -eq "unauthorized_global_role_change" } | Select-Object -First 1
    if (-not $bobAlert) {
        Write-Host "        (warning: expected alert from Bob's earlier 403 not found -- skipping alert-resolution tests)" -ForegroundColor DarkYellow
    } else {
        $alertId = $bobAlert.id

        Invoke-ApiTest -Name "Site admin resolves the security alert" -Method PATCH -Endpoint "/admin/alerts/$alertId/resolve" -ExpectedStatus 200 `
            -Headers $adminAuth `
            -Validate { param($r) if (-not $r.resolved) { throw "alert was not marked resolved" } }

        Invoke-ApiTest -Name "Resolved alert no longer appears in the unresolved list" -Method GET -Endpoint "/admin/alerts?include_resolved=false" -ExpectedStatus 200 `
            -Headers $adminAuth `
            -Validate { param($r) if (@($r) | Where-Object { $_.id -eq $alertId }) { throw "resolved alert still showing as unresolved" } }

        Invoke-ApiTest -Name "Resolved alert appears when include_resolved=true" -Method GET -Endpoint "/admin/alerts?include_resolved=true" -ExpectedStatus 200 `
            -Headers $adminAuth `
            -Validate { param($r) if (-not (@($r) | Where-Object { $_.id -eq $alertId -and $_.resolved })) { throw "resolved alert missing from full list" } }
    }

    Invoke-ApiTest -Name "Resolving a nonexistent alert 404s (not 403 -- caller IS admin)" -Method PATCH -Endpoint "/admin/alerts/does-not-exist/resolve" -ExpectedStatus 404 `
        -Headers $adminAuth

    # GlobalRole only has "admin" and "member" now -- "manager" is gone.
    # PATCH /users/{id}/role no longer allows setting global_role=admin directly --
    # it redirects callers to POST /admin/transfer-admin (see users.py). The actual
    # promote-to-admin success path is covered in the transfer-admin block below.
    Invoke-ApiTest -Name "PATCH /users/{id}/role rejects setting admin -- redirects to transfer-admin" -Method PATCH -Endpoint "/users/$carolId/role" -ExpectedStatus 400 `
        -Headers $adminAuth -Body @{ global_role = "admin" } `
        -Validate { param($r) if ($r.detail -notmatch "transfer-admin") { throw "expected detail to point at /admin/transfer-admin, got '$($r.detail)'" } }

    Invoke-ApiTest -Name "Site admin demotes Carol back to member (cleanup)" -Method PATCH -Endpoint "/users/$carolId/role" -ExpectedStatus 200 `
        -Headers $adminAuth -Body @{ global_role = "member" } `
        -Validate { param($r) if ($r.global_role -ne "member") { throw "role was not reverted" } }

    Invoke-ApiTest -Name "Site admin bypasses membership -- can view project A without joining" -Method GET -Endpoint "/projects/$projectAId" -ExpectedStatus 200 `
        -Headers $adminAuth

    Invoke-ApiTest -Name "Site admin bypasses membership -- can edit project A without joining" -Method PATCH -Endpoint "/projects/$projectAId" -ExpectedStatus 200 `
        -Headers $adminAuth -Body @{ description = "Touched by site admin during testing" }

    Invoke-ApiTest -Name "Site admin's project list includes projects they don't belong to" -Method GET -Endpoint "/projects/?limit=200&offset=0" -ExpectedStatus 200 `
        -Headers $adminAuth `
        -Validate { param($r) if (-not (@($r) | Where-Object { $_.id -eq $projectAId })) { throw "admin's project list is missing project A despite not being a member" } }

    # ---- Site-wide admin transfer (POST /admin/transfer-admin) ----
    $adminMe = Invoke-ApiTest -Name "Get admin's own id (for transfer tests)" -Method GET -Endpoint "/users/me" -ExpectedStatus 200 `
        -Headers $adminAuth
    $realAdminId = $adminMe.id

    Invoke-ApiTest -Name "Transfer-admin to a nonexistent user 404s" -Method POST -Endpoint "/admin/transfer-admin" -ExpectedStatus 404 `
        -Headers $adminAuth -Body @{ new_admin_user_id = "does-not-exist" }

    Invoke-ApiTest -Name "Transferring admin to yourself is rejected" -Method POST -Endpoint "/admin/transfer-admin" -ExpectedStatus 400 `
        -Headers $adminAuth -Body @{ new_admin_user_id = $realAdminId }

    Invoke-ApiTest -Name "Site admin transfers admin rights to Carol" -Method POST -Endpoint "/admin/transfer-admin" -ExpectedStatus 200 `
        -Headers $adminAuth -Body @{ new_admin_user_id = $carolId } `
        -Validate { param($r) if ($r.global_role -ne "admin" -or $r.id -ne $carolId) { throw "expected Carol to become admin" } }

    Invoke-ApiTest -Name "Old admin token loses admin access right after transfer" -Method GET -Endpoint "/admin/alerts?include_resolved=false" -ExpectedStatus 403 `
        -Headers $adminAuth

    Invoke-ApiTest -Name "Carol's own profile now shows global admin" -Method GET -Endpoint "/users/me" -ExpectedStatus 200 `
        -Headers $carolAuth -Validate { param($r) if ($r.global_role -ne "admin") { throw "Carol's token does not reflect the new admin role" } }

    Invoke-ApiTest -Name "Carol transfers admin rights back to the real admin" -Method POST -Endpoint "/admin/transfer-admin" -ExpectedStatus 200 `
        -Headers $carolAuth -Body @{ new_admin_user_id = $realAdminId } `
        -Validate { param($r) if ($r.global_role -ne "admin" -or $r.id -ne $realAdminId) { throw "admin role was not restored" } }

    Invoke-ApiTest -Name "Real admin access restored after transfer-back" -Method GET -Endpoint "/admin/alerts?include_resolved=false" -ExpectedStatus 200 `
        -Headers $adminAuth

    Invoke-ApiTest -Name "Carol is back to a regular member" -Method GET -Endpoint "/users/me" -ExpectedStatus 200 `
        -Headers $carolAuth -Validate { param($r) if ($r.global_role -ne "member") { throw "Carol was not demoted back to member" } }
} else {
    Write-Host ""
    Write-Host "--- Phase 6.5: Admin-Privileged Actions (SKIPPED -- pass -AdminEmail/-AdminPassword to enable) ---" -ForegroundColor DarkGray
}

# ===========================================================================
# PHASE 7 - Cleanup, ordered so the business rules under test actually fire
# ===========================================================================
Write-Host ""
Write-Host "--- Phase 7: Cleanup & Last-Admin Protection ---" -ForegroundColor Magenta

Invoke-ApiTest -Name "Unassign Bob from task 1" -Method DELETE -Endpoint "/tasks/$task1Id/assign/$bobId" -ExpectedStatus 204 `
    -Headers $bobAuth

Invoke-ApiTest -Name "Contributor cannot remove another member (needs manager+)" -Method DELETE -Endpoint "/projects/$projectAId/members/$carolId" -ExpectedStatus 403 `
    -Headers $bobAuth

Invoke-ApiTest -Name "Carol (viewer, not last admin) can leave project A" -Method DELETE -Endpoint "/projects/$projectAId/leave" -ExpectedStatus 204 `
    -Headers $carolAuth

Invoke-ApiTest -Name "Sole project admin is blocked from leaving (last-admin rule)" -Method DELETE -Endpoint "/projects/$projectAId/leave" -ExpectedStatus 400 `
    -Headers $aliceAuth

Invoke-ApiTest -Name "Cannot delete a project that still has tasks" -Method DELETE -Endpoint "/projects/$projectAId" -ExpectedStatus 400 `
    -Headers $aliceAuth

Invoke-ApiTest -Name "Delete task 2 in project A" -Method DELETE -Endpoint "/tasks/$task2Id" -ExpectedStatus 204 -Headers $aliceAuth
Invoke-ApiTest -Name "Delete task 1 in project A" -Method DELETE -Endpoint "/tasks/$task1Id" -ExpectedStatus 204 -Headers $aliceAuth

Invoke-ApiTest -Name "Bob (contributor, not admin) can leave project A" -Method DELETE -Endpoint "/projects/$projectAId/leave" -ExpectedStatus 204 `
    -Headers $bobAuth

Invoke-ApiTest -Name "Delete now-empty project A" -Method DELETE -Endpoint "/projects/$projectAId" -ExpectedStatus 204 -Headers $aliceAuth

Invoke-ApiTest -Name "Cannot delete project B while its task still exists" -Method DELETE -Endpoint "/projects/$projectBId" -ExpectedStatus 400 `
    -Headers $bobAuth
Invoke-ApiTest -Name "Delete the task in project B" -Method DELETE -Endpoint "/tasks/$taskInBId" -ExpectedStatus 204 -Headers $bobAuth
Invoke-ApiTest -Name "Delete now-empty project B" -Method DELETE -Endpoint "/projects/$projectBId" -ExpectedStatus 204 -Headers $bobAuth

# ===========================================================================
# Summary report
# ===========================================================================
Write-Host ""
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host " TEST SUMMARY" -ForegroundColor Cyan
Write-Host "===================================================================" -ForegroundColor Cyan

$passCount = @($script:Results | Where-Object { $_.Passed }).Count
$failCount = @($script:Results | Where-Object { -not $_.Passed }).Count

Write-Host "Total tests run : $($script:TestCount)"
Write-Host "Passed          : $passCount" -ForegroundColor Green
Write-Host "Failed          : $failCount" -ForegroundColor $(if ($failCount -gt 0) { "Red" } else { "Green" })

if ($failCount -gt 0) {
    Write-Host ""
    Write-Host "Failed tests:" -ForegroundColor Red
    $script:Results |
        Where-Object { -not $_.Passed } |
        Select-Object TestName, Line, Endpoint, ExpectedStatus, ActualStatus, Detail |
        Format-Table -AutoSize -Wrap
}

Write-Host "===================================================================" -ForegroundColor Cyan

if ($failCount -gt 0) {
    exit 1
} else {
    Write-Host "All tests passed." -ForegroundColor Green
    exit 0
}