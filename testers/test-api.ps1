# ==========================================================================
# Team Task Management API - full end-to-end smoke test (PowerShell)
# Run against a locally running server: python -m uvicorn app.main:app --reload
#
# Covers every route in the app, including the endpoints added after the
# original test-api.ps1 was written:
#   - PATCH /users/me
#   - PATCH /users/{id}/role      (global admin role management)
#   - GET  /tasks/{id}/history
#   - GET  /tasks/project/{id}    with status / priority / assignee_id / limit / offset
#   - GET  /projects/             with status / limit / offset
#   - DELETE /projects/{id}/leave
#   - GET  /comments/task/{id}    now returns a nested reply tree, not a flat list
# ==========================================================================

$Base = "http://127.0.0.1:8000"
$Global:Issues = @()
$Global:CurrentSection = "Initialization"

function Section($title) {
    $Global:CurrentSection = $title
    Write-Host ""
    Write-Host "==== $title ====" -ForegroundColor Cyan
}

function ShouldFail($title, $scriptBlock) {
    # Wraps a call that is EXPECTED to throw (403/400/etc). Confirms it did.
    try {
        & $scriptBlock
        Write-Host "  [ISSUE] $title succeeded but should have failed!" -ForegroundColor Red
        $Global:Issues += "[$Global:CurrentSection] $title : expected a rejection (403/400/404) but the call succeeded"
    } catch {
        $status = $_.Exception.Response.StatusCode.value__
        Write-Host "  [OK] $title correctly rejected (HTTP $status)" -ForegroundColor Green
    }
}

function Expect($title, $condition) {
    # Asserts a boolean condition computed from a response body (counts, values, etc.)
    if ($condition) {
        Write-Host "  [OK] $title" -ForegroundColor Green
    } else {
        Write-Host "  [ISSUE] $title" -ForegroundColor Red
        $Global:Issues += "[$Global:CurrentSection] $title : assertion failed"
    }
}

try {

    # ----------------------------------------------------------------------
    Section "1. Register two users"
    # ----------------------------------------------------------------------
    $ownerEmail   = "owner_$(Get-Random)@test.com"
    $memberEmail  = "member_$(Get-Random)@test.com"
    $password     = "TestPass123!"

    $owner = Invoke-RestMethod -Method Post -Uri "$Base/auth/register" -ContentType "application/json" -Body (@{
        name = "Project Owner"; email = $ownerEmail; password = $password
    } | ConvertTo-Json)
    Write-Host "  Registered owner: $($owner.email) (id: $($owner.id))"

    $member = Invoke-RestMethod -Method Post -Uri "$Base/auth/register" -ContentType "application/json" -Body (@{
        name = "Team Member"; email = $memberEmail; password = $password
    } | ConvertTo-Json)
    Write-Host "  Registered member: $($member.email) (id: $($member.id))"

    # ----------------------------------------------------------------------
    Section "2. Login as both users"
    # ----------------------------------------------------------------------
    # /auth/login expects OAuth2 form data (username + password), not JSON
    $ownerLogin = Invoke-RestMethod -Method Post -Uri "$Base/auth/login" -ContentType "application/x-www-form-urlencoded" -Body @{
        username = $ownerEmail; password = $password
    }
    $ownerToken = $ownerLogin.access_token
    $ownerHeaders = @{ Authorization = "Bearer $ownerToken" }
    Write-Host "  Owner token acquired"

    $memberLogin = Invoke-RestMethod -Method Post -Uri "$Base/auth/login" -ContentType "application/x-www-form-urlencoded" -Body @{
        username = $memberEmail; password = $password
    }
    $memberToken = $memberLogin.access_token
    $memberHeaders = @{ Authorization = "Bearer $memberToken" }
    Write-Host "  Member token acquired"

    # ----------------------------------------------------------------------
    Section "3. GET /users/me for both"
    # ----------------------------------------------------------------------
    $me = Invoke-RestMethod -Method Get -Uri "$Base/users/me" -Headers $ownerHeaders
    Write-Host "  /users/me (owner) -> $($me.email), global_role: $($me.global_role)"

    # ----------------------------------------------------------------------
    Section "4. PATCH /users/me - update own profile"
    # ----------------------------------------------------------------------
    $updatedMe = Invoke-RestMethod -Method Patch -Uri "$Base/users/me" -Headers $ownerHeaders -ContentType "application/json" -Body (@{
        name = "Project Owner (Updated)"
    } | ConvertTo-Json)
    Expect "Name updated via PATCH /users/me" ($updatedMe.name -eq "Project Owner (Updated)")

    # password change + relogin proves the new password actually works
    Invoke-RestMethod -Method Patch -Uri "$Base/users/me" -Headers $ownerHeaders -ContentType "application/json" -Body (@{
        password = "NewPass456!"
    } | ConvertTo-Json) | Out-Null
    $reloginAfterPwChange = Invoke-RestMethod -Method Post -Uri "$Base/auth/login" -ContentType "application/x-www-form-urlencoded" -Body @{
        username = $ownerEmail; password = "NewPass456!"
    }
    Expect "Login succeeds with new password" ($null -ne $reloginAfterPwChange.access_token)
    $ownerToken = $reloginAfterPwChange.access_token
    $ownerHeaders = @{ Authorization = "Bearer $ownerToken" }

    ShouldFail "Old password no longer works" {
        Invoke-RestMethod -Method Post -Uri "$Base/auth/login" -ContentType "application/x-www-form-urlencoded" -Body @{
            username = $ownerEmail; password = $password
        }
    }
    # restore original password so the rest of the script's assumptions hold
    Invoke-RestMethod -Method Patch -Uri "$Base/users/me" -Headers $ownerHeaders -ContentType "application/json" -Body (@{
        password = $password
    } | ConvertTo-Json) | Out-Null

    # ----------------------------------------------------------------------
    Section "5. Global admin role management (PATCH /users/{id}/role)"
    # ----------------------------------------------------------------------
    # Only the very first user ever registered on a fresh database is
    # bootstrapped as a global admin. This branch adapts to whichever
    # state the target DB is actually in, so the script is safe to run
    # repeatedly against the same server.
    if ($me.global_role -eq "admin") {
        Write-Host "  Owner is bootstrapped as global admin - testing promotion path"
        $promotedGlobal = Invoke-RestMethod -Method Patch -Uri "$Base/users/$($member.id)/role" -Headers $ownerHeaders -ContentType "application/json" -Body (@{
            global_role = "manager"
        } | ConvertTo-Json)
        Expect "Admin promotes member to global manager" ($promotedGlobal.global_role -eq "manager")

        ShouldFail "Newly-promoted manager cannot self-promote to admin" {
            Invoke-RestMethod -Method Patch -Uri "$Base/users/$($member.id)/role" -Headers $memberHeaders -ContentType "application/json" -Body (@{
                global_role = "admin"
            } | ConvertTo-Json)
        }

        # revert so member's global role doesn't affect anything downstream
        Invoke-RestMethod -Method Patch -Uri "$Base/users/$($member.id)/role" -Headers $ownerHeaders -ContentType "application/json" -Body (@{
            global_role = "member"
        } | ConvertTo-Json) | Out-Null
    } else {
        Write-Host "  Owner is a regular member on this run (DB already has a bootstrapped admin) - testing rejection path only"
        ShouldFail "Non-site-admin owner cannot change roles" {
            Invoke-RestMethod -Method Patch -Uri "$Base/users/$($member.id)/role" -Headers $ownerHeaders -ContentType "application/json" -Body (@{
                global_role = "manager"
            } | ConvertTo-Json)
        }
    }

    ShouldFail "Non-site-admin member cannot change their own role" {
        Invoke-RestMethod -Method Patch -Uri "$Base/users/$($member.id)/role" -Headers $memberHeaders -ContentType "application/json" -Body (@{
            global_role = "admin"
        } | ConvertTo-Json)
    }

    # ----------------------------------------------------------------------
    Section "6. Create a project (as owner)"
    # ----------------------------------------------------------------------
    $project = Invoke-RestMethod -Method Post -Uri "$Base/projects/" -Headers $ownerHeaders -ContentType "application/json" -Body (@{
        name = "Launch Website"; description = "Get the new site live"
    } | ConvertTo-Json)
    $projectId = $project.id
    Write-Host "  Created project: $($project.name) (id: $projectId)"
    Write-Host ($project | ConvertTo-Json)

    # ----------------------------------------------------------------------
    Section "7. List / filter / paginate my projects"
    # ----------------------------------------------------------------------
    $myProjects = Invoke-RestMethod -Method Get -Uri "$Base/projects/" -Headers $ownerHeaders
    Write-Host "  Owner has $($myProjects.Count) project(s)"

    $activeProjects = Invoke-RestMethod -Method Get -Uri "$Base/projects/?status=active" -Headers $ownerHeaders
    $activeMatch = @($activeProjects | Where-Object { $_.id -eq $projectId })
    Expect "status=active includes the new project" ($activeMatch.Count -eq 1)

    $archivedProjects = Invoke-RestMethod -Method Get -Uri "$Base/projects/?status=archived" -Headers $ownerHeaders
    $archivedMatch = @($archivedProjects | Where-Object { $_.id -eq $projectId })
    Expect "status=archived excludes the (active) new project" ($archivedMatch.Count -eq 0)

    $pagedProjects = Invoke-RestMethod -Method Get -Uri "$Base/projects/?limit=1&offset=0" -Headers $ownerHeaders
    Expect "limit=1 returns at most 1 project" ($pagedProjects.Count -le 1)

    $fetched = Invoke-RestMethod -Method Get -Uri "$Base/projects/$projectId" -Headers $ownerHeaders
    Write-Host "  Fetched project by id: $($fetched.name)"

    # ----------------------------------------------------------------------
    Section "8. Non-member tries to access the project -> should be 403"
    # ----------------------------------------------------------------------
    ShouldFail "Non-member GET /projects/{id}" {
        Invoke-RestMethod -Method Get -Uri "$Base/projects/$projectId" -Headers $memberHeaders
    }

    # ----------------------------------------------------------------------
    Section "9. Look up the member by email, then add them to the project"
    # ----------------------------------------------------------------------
    $lookedUp = Invoke-RestMethod -Method Get -Uri "$Base/users/lookup?email=$memberEmail" -Headers $ownerHeaders
    Write-Host "  Looked up member id: $($lookedUp.id)"

    $addedMember = Invoke-RestMethod -Method Post -Uri "$Base/projects/$projectId/members" -Headers $ownerHeaders -ContentType "application/json" -Body (@{
        user_id = $lookedUp.id; project_role = "contributor"
    } | ConvertTo-Json)
    Write-Host "  Added member with role: $($addedMember.project_role)"

    ShouldFail "Adding the same member twice" {
        Invoke-RestMethod -Method Post -Uri "$Base/projects/$projectId/members" -Headers $ownerHeaders -ContentType "application/json" -Body (@{
            user_id = $lookedUp.id; project_role = "contributor"
        } | ConvertTo-Json)
    }

    Write-Host "  Confirming member can now access the project..."
    $fetchedAsMember = Invoke-RestMethod -Method Get -Uri "$Base/projects/$projectId" -Headers $memberHeaders
    Write-Host "  Member can now see project: $($fetchedAsMember.name)"

    # ----------------------------------------------------------------------
    Section "10. Create a task"
    # ----------------------------------------------------------------------
    $task = Invoke-RestMethod -Method Post -Uri "$Base/tasks/" -Headers $ownerHeaders -ContentType "application/json" -Body (@{
        project_id = $projectId; title = "Design homepage"; description = "Above-the-fold hero + nav"; priority = "high"; due_date = "2026-09-01"
    } | ConvertTo-Json)
    $taskId = $task.id
    Write-Host "  Created task: $($task.title) (id: $taskId, status: $($task.status))"

    # ----------------------------------------------------------------------
    Section "11. List tasks for project / get task by id"
    # ----------------------------------------------------------------------
    $tasksForProject = Invoke-RestMethod -Method Get -Uri "$Base/tasks/project/$projectId" -Headers $ownerHeaders
    Write-Host "  Project has $($tasksForProject.Count) task(s)"

    $fetchedTask = Invoke-RestMethod -Method Get -Uri "$Base/tasks/$taskId" -Headers $ownerHeaders
    Write-Host "  Fetched task: $($fetchedTask.title)"

    # ----------------------------------------------------------------------
    Section "12. Assign the member to the task"
    # ----------------------------------------------------------------------
    $assignUri = "$Base/tasks/$taskId/assign?user_id=$($lookedUp.id)"
    $assignResult = Invoke-RestMethod -Method Post -Uri $assignUri -Headers $ownerHeaders
    Write-Host "  $($assignResult.detail)"

    ShouldFail "Assigning the same user twice" {
        Invoke-RestMethod -Method Post -Uri $assignUri -Headers $ownerHeaders
    }

    # ----------------------------------------------------------------------
    Section "13. Update task status (PATCH) -> in_progress, then done"
    # ----------------------------------------------------------------------
    $updated = Invoke-RestMethod -Method Patch -Uri "$Base/tasks/$taskId" -Headers $memberHeaders -ContentType "application/json" -Body (@{
        status = "in_progress"
    } | ConvertTo-Json)
    Write-Host "  Task status -> $($updated.status)"

    $updated2 = Invoke-RestMethod -Method Patch -Uri "$Base/tasks/$taskId" -Headers $memberHeaders -ContentType "application/json" -Body (@{
        status = "done"
    } | ConvertTo-Json)
    Write-Host "  Task status -> $($updated2.status)"

    # ----------------------------------------------------------------------
    Section "14. GET /tasks/{id}/history - status change audit trail"
    # ----------------------------------------------------------------------
    $history = Invoke-RestMethod -Method Get -Uri "$Base/tasks/$taskId/history" -Headers $ownerHeaders
    Write-Host "  $($history.Count) history entries: $($history.new_status -join ' -> ')"
    Expect "History has 3 entries (create + 2 status changes)" ($history.Count -eq 3)
    Expect "First entry is the initial 'todo' with no old_status" ($history[0].new_status -eq "todo" -and $null -eq $history[0].old_status)
    Expect "Last entry lands on 'done'" ($history[-1].new_status -eq "done")

    # ----------------------------------------------------------------------
    Section "15. Task filtering & pagination (GET /tasks/project/{id})"
    # ----------------------------------------------------------------------
    $filterTask = Invoke-RestMethod -Method Post -Uri "$Base/tasks/" -Headers $ownerHeaders -ContentType "application/json" -Body (@{
        project_id = $projectId; title = "Low priority cleanup"; priority = "low"
    } | ConvertTo-Json)
    Write-Host "  Created a second task (priority: low) for filter testing"

    $byPriorityLow = Invoke-RestMethod -Method Get -Uri "$Base/tasks/project/$($projectId)?priority=low" -Headers $ownerHeaders
    Expect "priority=low returns exactly the cleanup task" ($byPriorityLow.Count -eq 1 -and $byPriorityLow[0].id -eq $filterTask.id)

    $byStatusDone = Invoke-RestMethod -Method Get -Uri "$Base/tasks/project/$($projectId)?status=done" -Headers $ownerHeaders
    Expect "status=done returns exactly the homepage task" ($byStatusDone.Count -eq 1 -and $byStatusDone[0].id -eq $taskId)

    $byAssignee = Invoke-RestMethod -Method Get -Uri "$Base/tasks/project/$($projectId)?assignee_id=$($lookedUp.id)" -Headers $ownerHeaders
    Expect "assignee_id filter returns the assigned task" ($byAssignee.Count -eq 1 -and $byAssignee[0].id -eq $taskId)

    $pagedTasks = Invoke-RestMethod -Method Get -Uri "$Base/tasks/project/$($projectId)?limit=1" -Headers $ownerHeaders
    Expect "limit=1 returns at most 1 task" ($pagedTasks.Count -le 1)

    Invoke-RestMethod -Method Delete -Uri "$Base/tasks/$($filterTask.id)" -Headers $ownerHeaders | Out-Null
    Write-Host "  Cleaned up the filter-test task"

    # ----------------------------------------------------------------------
    Section "16. Unassign the member from the task"
    # ----------------------------------------------------------------------
    Invoke-RestMethod -Method Delete -Uri "$Base/tasks/$taskId/assign/$($lookedUp.id)" -Headers $ownerHeaders
    Write-Host "  Unassigned OK"

    ShouldFail "Unassigning again (not assigned anymore)" {
        Invoke-RestMethod -Method Delete -Uri "$Base/tasks/$taskId/assign/$($lookedUp.id)" -Headers $ownerHeaders
    }

    # ----------------------------------------------------------------------
    Section "17. Comments: create, nested replies, list-as-tree, edit, delete"
    # ----------------------------------------------------------------------
    $comment = Invoke-RestMethod -Method Post -Uri "$Base/comments/" -Headers $ownerHeaders -ContentType "application/json" -Body (@{
        task_id = $taskId; content = "Looks good, ship it"
    } | ConvertTo-Json)
    Write-Host "  Created root comment (id: $($comment.id))"

    $reply = Invoke-RestMethod -Method Post -Uri "$Base/comments/" -Headers $memberHeaders -ContentType "application/json" -Body (@{
        task_id = $taskId; content = "Thanks! Deploying now"; parent_comment_id = $comment.id
    } | ConvertTo-Json)
    Write-Host "  Created reply (id: $($reply.id), parent: $($reply.parent_comment_id))"

    $grandchildReply = Invoke-RestMethod -Method Post -Uri "$Base/comments/" -Headers $ownerHeaders -ContentType "application/json" -Body (@{
        task_id = $taskId; content = "Confirmed live"; parent_comment_id = $reply.id
    } | ConvertTo-Json)
    Write-Host "  Created reply-to-reply (id: $($grandchildReply.id), parent: $($grandchildReply.parent_comment_id))"

    $commentTree = Invoke-RestMethod -Method Get -Uri "$Base/comments/task/$taskId" -Headers $ownerHeaders
    Expect "Tree has 1 root comment" ($commentTree.Count -eq 1)
    Expect "Root comment has 1 direct reply" ($commentTree[0].replies.Count -eq 1)
    Expect "Reply is correctly nested 2 levels deep" ($commentTree[0].replies[0].replies.Count -eq 1 -and $commentTree[0].replies[0].replies[0].id -eq $grandchildReply.id)

    ShouldFail "Editing someone else's comment" {
        Invoke-RestMethod -Method Patch -Uri "$Base/comments/$($comment.id)" -Headers $memberHeaders -ContentType "application/json" -Body (@{
            content = "hijacked"
        } | ConvertTo-Json)
    }

    $editedComment = Invoke-RestMethod -Method Patch -Uri "$Base/comments/$($comment.id)" -Headers $ownerHeaders -ContentType "application/json" -Body (@{
        content = "Looks good, ship it! (edited)"
    } | ConvertTo-Json)
    Write-Host "  Edited own comment -> '$($editedComment.content)'"

    Invoke-RestMethod -Method Delete -Uri "$Base/comments/$($grandchildReply.id)" -Headers $ownerHeaders
    Write-Host "  Deleted own leaf reply OK"

    # ----------------------------------------------------------------------
    Section "18. Project stats"
    # ----------------------------------------------------------------------
    $stats = Invoke-RestMethod -Method Get -Uri "$Base/projects/$projectId/stats" -Headers $ownerHeaders
    Write-Host "  Total tasks: $($stats.total_tasks)"
    Write-Host "  By status: $($stats.tasks_by_status | ConvertTo-Json -Compress)"
    Write-Host "  Overdue: $($stats.overdue_tasks)"

    # ----------------------------------------------------------------------
    Section "19. Register a third user and add as contributor (future manager)"
    # ----------------------------------------------------------------------
    $managerEmail = "manager_$(Get-Random)@test.com"
    $managerUser = Invoke-RestMethod -Method Post -Uri "$Base/auth/register" -ContentType "application/json" -Body (@{
        name = "Future Manager"; email = $managerEmail; password = $password
    } | ConvertTo-Json)

    $managerLogin = Invoke-RestMethod -Method Post -Uri "$Base/auth/login" -ContentType "application/x-www-form-urlencoded" -Body @{
        username = $managerEmail; password = $password
    }
    $managerToken = $managerLogin.access_token
    $managerHeaders = @{ Authorization = "Bearer $managerToken" }

    $lookedUpManager = Invoke-RestMethod -Method Get -Uri "$Base/users/lookup?email=$managerEmail" -Headers $ownerHeaders
    Invoke-RestMethod -Method Post -Uri "$Base/projects/$projectId/members" -Headers $ownerHeaders -ContentType "application/json" -Body (@{
        user_id = $lookedUpManager.id; project_role = "contributor"
    } | ConvertTo-Json) | Out-Null
    Write-Host "  Registered and added future manager as contributor (id: $($lookedUpManager.id))"

    # ----------------------------------------------------------------------
    Section "20. Contributor cannot change anyone's project role"
    # ----------------------------------------------------------------------
    ShouldFail "Contributor PATCHing another member's role" {
        Invoke-RestMethod -Method Patch -Uri "$Base/projects/$projectId/members/$($lookedUpManager.id)" -Headers $memberHeaders -ContentType "application/json" -Body (@{
            project_role = "manager"
        } | ConvertTo-Json)
    }

    # ----------------------------------------------------------------------
    Section "21. Admin (project creator) promotes the third user to manager"
    # ----------------------------------------------------------------------
    $promoted = Invoke-RestMethod -Method Patch -Uri "$Base/projects/$projectId/members/$($lookedUpManager.id)" -Headers $ownerHeaders -ContentType "application/json" -Body (@{
        project_role = "manager"
    } | ConvertTo-Json)
    Write-Host "  Promoted to: $($promoted.project_role)"

    # ----------------------------------------------------------------------
    Section "22. Manager cannot grant the admin role"
    # ----------------------------------------------------------------------
    ShouldFail "Manager promoting a member to admin" {
        Invoke-RestMethod -Method Patch -Uri "$Base/projects/$projectId/members/$($lookedUp.id)" -Headers $managerHeaders -ContentType "application/json" -Body (@{
            project_role = "admin"
        } | ConvertTo-Json)
    }

    # ----------------------------------------------------------------------
    Section "23. Manager CAN change a contributor to viewer and back"
    # ----------------------------------------------------------------------
    $demoted = Invoke-RestMethod -Method Patch -Uri "$Base/projects/$projectId/members/$($lookedUp.id)" -Headers $managerHeaders -ContentType "application/json" -Body (@{
        project_role = "viewer"
    } | ConvertTo-Json)
    Write-Host "  Member demoted to: $($demoted.project_role)"

    ShouldFail "Viewer creating a task" {
        Invoke-RestMethod -Method Post -Uri "$Base/tasks/" -Headers $memberHeaders -ContentType "application/json" -Body (@{
            project_id = $projectId; title = "Should not be created"
        } | ConvertTo-Json)
    }

    $restored = Invoke-RestMethod -Method Patch -Uri "$Base/projects/$projectId/members/$($lookedUp.id)" -Headers $managerHeaders -ContentType "application/json" -Body (@{
        project_role = "contributor"
    } | ConvertTo-Json)
    Write-Host "  Member restored to: $($restored.project_role)"

    # ----------------------------------------------------------------------
    Section "24. List project members"
    # ----------------------------------------------------------------------
    $members = Invoke-RestMethod -Method Get -Uri "$Base/projects/$projectId/members" -Headers $ownerHeaders
    Write-Host "  Project has $($members.Count) member(s):"
    foreach ($m in $members) { Write-Host "    - $($m.user_id): $($m.project_role)" }

    # ----------------------------------------------------------------------
    Section "25. Contributor can update task status but not other fields"
    # ----------------------------------------------------------------------
    $extraTask = Invoke-RestMethod -Method Post -Uri "$Base/tasks/" -Headers $memberHeaders -ContentType "application/json" -Body (@{
        project_id = $projectId; title = "Write tests"
    } | ConvertTo-Json)
    $extraTaskId = $extraTask.id
    Write-Host "  Contributor created task: $($extraTask.title) (id: $extraTaskId)"

    ShouldFail "Contributor editing task title" {
        Invoke-RestMethod -Method Patch -Uri "$Base/tasks/$extraTaskId" -Headers $memberHeaders -ContentType "application/json" -Body (@{
            title = "Hijacked title"
        } | ConvertTo-Json)
    }

    $statusOnly = Invoke-RestMethod -Method Patch -Uri "$Base/tasks/$extraTaskId" -Headers $memberHeaders -ContentType "application/json" -Body (@{
        status = "in_progress"
    } | ConvertTo-Json)
    Write-Host "  Contributor set status-only update -> $($statusOnly.status)"

    $managerEdit = Invoke-RestMethod -Method Patch -Uri "$Base/tasks/$extraTaskId" -Headers $managerHeaders -ContentType "application/json" -Body (@{
        title = "Write unit tests"
    } | ConvertTo-Json)
    Write-Host "  Manager full-field edit -> '$($managerEdit.title)'"

    # ----------------------------------------------------------------------
    Section "26. Assigned-to-me and task delete (contributor, basic perms)"
    # ----------------------------------------------------------------------
    Invoke-RestMethod -Method Post -Uri "$Base/tasks/$extraTaskId/assign?user_id=$($lookedUp.id)" -Headers $memberHeaders | Out-Null
    Write-Host "  Contributor self-assigned to their task"

    $myTasks = Invoke-RestMethod -Method Get -Uri "$Base/tasks/assigned/me" -Headers $memberHeaders
    Write-Host "  Member has $($myTasks.Count) task(s) assigned to them"

    Invoke-RestMethod -Method Delete -Uri "$Base/tasks/$extraTaskId" -Headers $memberHeaders
    Write-Host "  Contributor deleted their own task OK"

    ShouldFail "Fetching a deleted task" {
        Invoke-RestMethod -Method Get -Uri "$Base/tasks/$extraTaskId" -Headers $ownerHeaders
    }

    # ----------------------------------------------------------------------
    Section "27. Last-admin lockout: sole admin can't demote, remove, or leave"
    # ----------------------------------------------------------------------
    ShouldFail "Sole admin demoting themselves" {
        Invoke-RestMethod -Method Patch -Uri "$Base/projects/$projectId/members/$($owner.id)" -Headers $ownerHeaders -ContentType "application/json" -Body (@{
            project_role = "manager"
        } | ConvertTo-Json)
    }

    ShouldFail "Sole admin removing themselves via DELETE /members/{id}" {
        Invoke-RestMethod -Method Delete -Uri "$Base/projects/$projectId/members/$($owner.id)" -Headers $ownerHeaders
    }

    ShouldFail "Sole admin leaving via DELETE /projects/{id}/leave" {
        Invoke-RestMethod -Method Delete -Uri "$Base/projects/$projectId/leave" -Headers $ownerHeaders
    }

    # ----------------------------------------------------------------------
    Section "28. Self-service leave (DELETE /projects/{id}/leave)"
    # ----------------------------------------------------------------------
    Invoke-RestMethod -Method Delete -Uri "$Base/projects/$projectId/leave" -Headers $memberHeaders
    Write-Host "  Member left the project voluntarily"

    ShouldFail "Ex-member accessing the project after leaving" {
        Invoke-RestMethod -Method Get -Uri "$Base/projects/$projectId" -Headers $memberHeaders
    }

    ShouldFail "Leaving a project you already left" {
        Invoke-RestMethod -Method Delete -Uri "$Base/projects/$projectId/leave" -Headers $memberHeaders
    }

    # ----------------------------------------------------------------------
    Section "29. Admin removes the manager from the project"
    # ----------------------------------------------------------------------
    Invoke-RestMethod -Method Delete -Uri "$Base/projects/$projectId/members/$($lookedUpManager.id)" -Headers $ownerHeaders
    Write-Host "  Manager removed from project OK"

    ShouldFail "Removing a member who's already gone" {
        Invoke-RestMethod -Method Delete -Uri "$Base/projects/$projectId/members/$($lookedUpManager.id)" -Headers $ownerHeaders
    }

    # ----------------------------------------------------------------------
    Section "30. Project update / delete lifecycle"
    # ----------------------------------------------------------------------
    $renamed = Invoke-RestMethod -Method Patch -Uri "$Base/projects/$projectId" -Headers $ownerHeaders -ContentType "application/json" -Body (@{
        name = "Launch Website (v2)"; status = "active"
    } | ConvertTo-Json)
    Write-Host "  Admin renamed project -> $($renamed.name)"

    ShouldFail "Deleting a project that still has tasks" {
        Invoke-RestMethod -Method Delete -Uri "$Base/projects/$projectId" -Headers $ownerHeaders
    }

    Invoke-RestMethod -Method Delete -Uri "$Base/tasks/$taskId" -Headers $ownerHeaders
    Write-Host "  Deleted remaining task so the project can be cleaned up"

    Invoke-RestMethod -Method Delete -Uri "$Base/projects/$projectId" -Headers $ownerHeaders
    Write-Host "  Project deleted OK"

    ShouldFail "Fetching a deleted project" {
        Invoke-RestMethod -Method Get -Uri "$Base/projects/$projectId" -Headers $ownerHeaders
    }

} catch {
    # Anything that was expected to succeed but threw lands here. The run
    # stops here (later steps likely depend on state we never got), but the
    # summary below still reports what we know.
    $status = $_.Exception.Response.StatusCode.value__
    $msg = "Unexpected failure in [$($Global:CurrentSection)] (HTTP $status): $($_.Exception.Message)"
    Write-Host ""
    Write-Host "  [ISSUE] $msg" -ForegroundColor Red
    $Global:Issues += $msg
}

# ==========================================================================
Section "SUMMARY"
# ==========================================================================
Write-Host "Full API Smoke Test Run Complete." -ForegroundColor Cyan

if ($Global:Issues.Count -eq 0) {
    Write-Host "  [RESULT] SUCCESS: 0 issues found. All API tests passed!" -ForegroundColor Green
} else {
    Write-Host "  [RESULT] FAILED: $($Global:Issues.Count) issue(s) found during execution." -ForegroundColor Red
    Write-Host "  Breakdown of parts that bugged out:" -ForegroundColor Yellow

    $counter = 1
    foreach ($issue in $Global:Issues) {
        Write-Host "   $counter. $issue" -ForegroundColor Red
        $counter++
    }

    # Exit with a non-zero code so automation tools (like GitHub Actions/GitLab CI) catch the failure
    exit 1
}