---
name: copilot_system_operations
description: Capabilities for modifying system state (Research Plan, etc.)
---

# System Operations Skill

You have the ability to modify the research plan and system state using server actions.

## Update Research Plan

When the user requests changes to the research objective, steps, or context, you MUST use the `update_plan` server action.

**Syntax:**
```xml
<server_action type="update_plan" job_id="job_123">
  {{
    "plan": {{
      "objective": "New Objective",
      "steps": ["Step 1", "Step 2"]
    }}
  }}
</server_action>
```

**Rules:**
- `job_id` is required. If the current job ID is available in the context, use it.
- The content inside the tag must be valid JSON.
- You can update `objective`, `steps`, `topic`, or any other field in the plan.
- Only update the fields that need changing.
