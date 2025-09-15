import os.path
from datetime import timedelta

import pytest
from django.utils import timezone

from courses.constants import AssignmentFormat
from courses.tests.factories import AssignmentFactory
from learning.models import StudentAssignment, AssignmentComment
from learning.services.jba_service import JbaService, JbaClient, JbaCourse
from learning.tests.factories import EnrollmentFactory

KOTLIN_KOANS_ID = 16628
with open(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kotlin_koans.json')
) as f:
    KOTLIN_KOANS_DATA = JbaCourse.model_validate_json(f.read())
TEST_JBA_ACCOUNT = 'test-jba@example.com'

HELLO_WORLD_TASK_ID = 234720
NAMED_ARGUMENTS_TASK_ID = 234722
DEFAULT_ARGUMENTS_TASK_ID = 234723
TASK_NAMES = {
    HELLO_WORLD_TASK_ID: 'Hello, world!',
    NAMED_ARGUMENTS_TASK_ID: 'Named arguments',
    DEFAULT_ARGUMENTS_TASK_ID: 'Default arguments',
}


class JbaMockClient(JbaClient):
    def __init__(self):
        self.solved_tasks = []

    def get_course(self, marketplace_id: int) -> JbaCourse | None:
        if marketplace_id == KOTLIN_KOANS_ID:
            return KOTLIN_KOANS_DATA
        return None

    def user_exists(self, email: str) -> bool:
        return email == TEST_JBA_ACCOUNT

    def get_course_progress(
        self, marketplace_id: int, emails: list[str]
    ) -> dict[str, list[int]]:
        if marketplace_id == KOTLIN_KOANS_ID and TEST_JBA_ACCOUNT in emails:
            return {TEST_JBA_ACCOUNT: self.solved_tasks}
        return {}


@pytest.fixture
def mock_jba_service(mocker):
    client = JbaMockClient()
    mocker.patch.object(JbaService, '_client', client)
    return client


@pytest.mark.django_db
def test_jba_requests(mock_jba_service):
    course = JbaService._client.get_course(KOTLIN_KOANS_ID)
    assert course is not None
    assert len(course.tasks) == 43

    data = JbaService._client.get_course_progress(KOTLIN_KOANS_ID, [TEST_JBA_ACCOUNT])
    assert data[TEST_JBA_ACCOUNT] == []
    mock_jba_service.solved_tasks = [HELLO_WORLD_TASK_ID, NAMED_ARGUMENTS_TASK_ID]
    data = JbaService._client.get_course_progress(KOTLIN_KOANS_ID, [TEST_JBA_ACCOUNT])
    assert data[TEST_JBA_ACCOUNT] == [HELLO_WORLD_TASK_ID, NAMED_ARGUMENTS_TASK_ID]


@pytest.mark.django_db
def test_update_assignment_progress(mock_jba_service):
    e = EnrollmentFactory(student__jetbrains_account=TEST_JBA_ACCOUNT)
    assignment = AssignmentFactory(
        course=e.course,
        submission_type=AssignmentFormat.JBA,
        jba_course_id=KOTLIN_KOANS_ID,
    )
    student_assignment = StudentAssignment.objects.get(
        assignment=assignment, student=e.student
    )

    def check_submissions(*, comment_count: int, solved_task_ids: list[int]):
        comments = (
            AssignmentComment.published.filter(student_assignment=student_assignment)
            .order_by('-created')
            .all()
        )
        assert len(comments) == comment_count
        last_comment = comments[0]
        assert last_comment.meta.get('jba_solved_task_ids') == solved_task_ids
        last_comment_text = last_comment.text
        assert f'**Total tasks**: {len(KOTLIN_KOANS_DATA.tasks)}' in last_comment_text
        assert f'**Solved tasks** ({len(solved_task_ids)})' in last_comment_text
        for k, v in TASK_NAMES.items():
            if k in solved_task_ids:
                assert v in last_comment_text
            else:
                assert v not in last_comment_text
        return last_comment

    JbaService.update_current_assignments_progress()
    check_submissions(comment_count=1, solved_task_ids=[])

    mock_jba_service.solved_tasks = [HELLO_WORLD_TASK_ID]
    JbaService.update_current_assignments_progress()
    check_submissions(comment_count=2, solved_task_ids=[HELLO_WORLD_TASK_ID])

    # Test that no comment is created if the progress has not changed
    JbaService.update_current_assignments_progress()
    check_submissions(comment_count=2, solved_task_ids=[HELLO_WORLD_TASK_ID])

    # Test that update_current_assignments_progress doesn't update assignments with a deadline in the past
    assignment.deadline_at = timezone.now() - timedelta(days=1)
    assignment.save()
    mock_jba_service.solved_tasks = [HELLO_WORLD_TASK_ID, NAMED_ARGUMENTS_TASK_ID]
    JbaService.update_current_assignments_progress()
    check_submissions(comment_count=2, solved_task_ids=[HELLO_WORLD_TASK_ID])

    # Test that update_assignment_progress with at_deadline=True creates a comment at the time of the deadline
    AssignmentComment.objects.all().delete()
    JbaService.update_assignment_progress(assignment, at_deadline=True)
    last_comment = check_submissions(
        comment_count=1, solved_task_ids=[HELLO_WORLD_TASK_ID, NAMED_ARGUMENTS_TASK_ID]
    )
    assert last_comment.created == assignment.deadline_at
