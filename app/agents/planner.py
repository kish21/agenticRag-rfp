"""
Planner Agent — decomposes an EvaluationSetup into a typed task DAG.
Does not retrieve, extract, or evaluate — only plans.
"""
import uuid
from app.core.output_models import EvaluationSetup, PlannerOutput, TaskItem


async def run_planner(
    rfp_id: str,
    org_id: str,
    vendor_ids: list[str],
    evaluation_setup: EvaluationSetup,
) -> PlannerOutput:
    """
    Builds a deterministic task DAG from evaluation_setup.
    Task IDs encode the check_id / criterion_id so validate_plan
    can verify coverage without relying on LLM-generated structure.
    """
    tasks: list[TaskItem] = []

    # 1. One retrieve task per vendor
    retrieve_ids = []
    for vendor_id in vendor_ids:
        tid = f"task-retrieve-{vendor_id}"
        tasks.append(TaskItem(
            task_id=tid,
            task_type="retrieve",
            agent="retrieval",
            inputs={"vendor_id": vendor_id, "rfp_id": rfp_id},
            depends_on=[],
            priority=1,
        ))
        retrieve_ids.append(tid)

    # 2. One extract task per vendor (depends on retrieve)
    extract_ids = []
    for vendor_id in vendor_ids:
        tid = f"task-extract-{vendor_id}"
        tasks.append(TaskItem(
            task_id=tid,
            task_type="extract",
            agent="extraction",
            inputs={
                "vendor_id": vendor_id,
                "extraction_target_ids": [
                    t.target_id for t in evaluation_setup.extraction_targets
                ],
            },
            depends_on=[f"task-retrieve-{vendor_id}"],
            priority=1,
        ))
        extract_ids.append(tid)

    # 3. One mandatory_check task per check — task_id encodes check_id
    check_ids = []
    for check in evaluation_setup.mandatory_checks:
        tid = f"task-check-{check.check_id}"
        tasks.append(TaskItem(
            task_id=tid,
            task_type="mandatory_check",
            agent="evaluation",
            inputs={"check_id": check.check_id, "vendor_ids": vendor_ids},
            depends_on=extract_ids,
            priority=1,
        ))
        check_ids.append(tid)

    # 4. One scoring task per criterion — task_id encodes criterion_id
    score_ids = []
    for criterion in evaluation_setup.scoring_criteria:
        tid = f"task-score-{criterion.criterion_id}"
        tasks.append(TaskItem(
            task_id=tid,
            task_type="scoring",
            agent="evaluation",
            inputs={"criterion_id": criterion.criterion_id, "vendor_ids": vendor_ids},
            depends_on=check_ids,
            priority=2,
        ))
        score_ids.append(tid)

    # 5. Compare, decide, explain — depend on all scoring tasks
    tasks.append(TaskItem(
        task_id="task-compare",
        task_type="compare",
        agent="comparator",
        inputs={"vendor_ids": vendor_ids},
        depends_on=score_ids,
        priority=2,
    ))
    tasks.append(TaskItem(
        task_id="task-decide",
        task_type="decide",
        agent="decision",
        inputs={"vendor_ids": vendor_ids},
        depends_on=["task-compare"],
        priority=3,
    ))
    tasks.append(TaskItem(
        task_id="task-explain",
        task_type="explain",
        agent="explanation",
        inputs={"vendor_ids": vendor_ids},
        depends_on=["task-decide"],
        priority=3,
    ))

    return PlannerOutput(
        plan_id=str(uuid.uuid4()),
        rfp_id=rfp_id,
        org_id=org_id,
        vendor_ids=vendor_ids,
        tasks=tasks,
        estimated_duration_seconds=len(tasks) * 30,
        confidence=1.0,
        warnings=[],
    )


def validate_plan(
    plan: PlannerOutput,
    evaluation_setup: EvaluationSetup,
) -> list[str]:
    """
    Planner guardrail. Returns a list of errors — empty means valid.
    Parses task_ids to verify every mandatory check and scoring criterion
    is covered, regardless of how the plan was generated.
    """
    errors = []

    if len(plan.tasks) < 5:
        errors.append(
            f"Plan has only {len(plan.tasks)} tasks — suspiciously low"
        )
    if len(plan.tasks) > 500:
        errors.append(
            f"Plan has {len(plan.tasks)} tasks — suspiciously high"
        )

    # Recover covered check_ids from task_ids with prefix "task-check-"
    covered_checks = set()
    for task in plan.tasks:
        if task.task_type == "mandatory_check" and task.task_id.startswith("task-check-"):
            covered_checks.add(task.task_id[len("task-check-"):])

    missing_checks = {
        c.check_id for c in evaluation_setup.mandatory_checks
    } - covered_checks
    if missing_checks:
        errors.append(
            f"Mandatory checks not covered by any task: {missing_checks}"
        )

    # Recover covered criterion_ids from task_ids with prefix "task-score-"
    covered_criteria = set()
    for task in plan.tasks:
        if task.task_type == "scoring" and task.task_id.startswith("task-score-"):
            covered_criteria.add(task.task_id[len("task-score-"):])

    missing_criteria = {
        c.criterion_id for c in evaluation_setup.scoring_criteria
    } - covered_criteria
    if missing_criteria:
        errors.append(
            f"Scoring criteria not covered by any task: {missing_criteria}"
        )

    # Check for circular dependencies
    task_map = {t.task_id: t for t in plan.tasks}
    visited: set[str] = set()

    def has_cycle(task_id: str, path: list[str] | None = None) -> bool:
        if path is None:
            path = []
        if task_id in path:
            return True
        if task_id in visited:
            return False
        visited.add(task_id)
        task = task_map.get(task_id)
        if not task:
            return False
        for dep in task.depends_on:
            if has_cycle(dep, path + [task_id]):
                return True
        return False

    for task in plan.tasks:
        if has_cycle(task.task_id):
            errors.append(
                f"Circular dependency detected involving task {task.task_id}"
            )
            break

    return errors
