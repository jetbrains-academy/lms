from abc import ABC, abstractmethod
from datetime import timedelta
from decimal import Decimal
from urllib.parse import urljoin, urlencode

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django_rq import get_queue
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from courses.constants import AssignmentFormat, AssignmentStatus
from courses.models import Assignment
from learning.models import StudentAssignment, AssignmentComment
from learning.services.jba_service_constants import ProgrammingLanguage, IDE_BY_LANGUAGE
from learning.services.personal_assignment_service import (
    create_personal_assignment_review,
    create_assignment_comment,
)
from learning.settings import AssignmentScoreUpdateSource


class JbaCourseTask(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    id: int = Field(alias='eduId')
    name: str
    type: str
    section_sequential_number: int | None
    lesson_sequential_number: int
    task_sequential_number: int


class JbaCourse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    id: int = Field(alias='marketplaceId')
    name: str
    update_version: int
    tasks: list[JbaCourseTask]


class JbaCourseInfo(BaseModel):
    id: int
    toolbox_link: str


class UnknownLanguage(ValueError):
    def __init__(self, language, *args):
        super().__init__(*args)
        self.language = language


class _JbaHttpClientSession(requests.Session):
    def __init__(self):
        super().__init__()
        self.headers = {'Authorization': f'Bearer {settings.SUBMISSION_SERVICE_TOKEN}'}

    def request(self, method, url, *args, **kwargs):
        full_url = urljoin(settings.SUBMISSION_SERVICE_URL, url)
        return super().request(method, full_url, *args, **kwargs)


class JbaClient(ABC):
    @abstractmethod
    def get_course(self, marketplace_id: int) -> JbaCourse | None: ...

    @abstractmethod
    def user_exists(self, email: str) -> bool: ...

    @abstractmethod
    def get_course_progress(
        self, marketplace_id: int, emails: list[str]
    ) -> dict[str, list[int]]: ...


class JbaHttpClient(JbaClient):
    def __init__(self):
        self.session = _JbaHttpClientSession()

    def get_course(self, marketplace_id: int) -> JbaCourse | None:
        response = self.session.get(f'/api/lms/course/{marketplace_id}/latest')
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = JbaCourse.model_validate(response.json())
        data.tasks.sort(
            key=lambda x: (
                x.section_sequential_number,
                x.lesson_sequential_number,
                x.task_sequential_number,
            )
        )
        return data

    def user_exists(self, email: str) -> bool:
        response = self.session.get('/api/lms/user', params={'email': email})
        return response.status_code == 200

    def get_course_progress(
        self, marketplace_id: int, emails: list[str]
    ) -> dict[str, list[int]]:
        response = self.session.post(
            f'/api/lms/course/{marketplace_id}/progress', json=emails
        )
        response.raise_for_status()
        data = response.json()
        return {x['email']: x['solvedTaskIds'] for x in data}


class JbaService:
    _client: JbaClient = JbaHttpClient()
    _cached_course_info = {}

    @staticmethod
    def get_course_info(jba_course_id: int) -> JbaCourseInfo:
        if jba_course_id in JbaService._cached_course_info:
            return JbaService._cached_course_info[jba_course_id]
        resp = requests.get(
            f'https://plugins.jetbrains.com/api/plugins/{jba_course_id}'
        )
        resp.raise_for_status()
        language_str = resp.json()['programmingLanguage']
        if not ProgrammingLanguage.contains(language_str):
            raise UnknownLanguage(language_str)
        language = ProgrammingLanguage(language_str)
        supported_ides = IDE_BY_LANGUAGE[language]
        toolbox_args = {
            'courseId': jba_course_id,
            'source': 'marketplace',
            'tools': ','.join(supported_ides),
            'minPluginVersion': '2025.1',
        }
        toolbox_link = 'jetbrains://educational?' + urlencode(toolbox_args)

        res = JbaCourseInfo(
            id=jba_course_id,
            toolbox_link=toolbox_link,
        )
        JbaService._cached_course_info[jba_course_id] = res
        return res

    @staticmethod
    def _generate_comment(
        jba_course_tasks: list[JbaCourseTask],
        solved_task_ids: list[int],
    ):
        lines = []
        for task in jba_course_tasks:
            if task.id not in solved_task_ids:
                continue
            if task.section_sequential_number is not None:
                line = f'{task.section_sequential_number}\.'
            else:
                line = ''
            line += f'{task.lesson_sequential_number}\.{task.task_sequential_number}\. {task.name} '
            lines.append(line)
        solved_tasks = '<br>'.join(lines)
        res = f'**Total tasks**: {len(jba_course_tasks)}\n\n'
        res += f'**Solved tasks** ({len(solved_task_ids)}):<br>'
        res += solved_tasks
        return res

    @staticmethod
    def update_assignment_progress(
        assignment: Assignment | int,
        *,
        user_ids: list[int] | None = None,
        at_deadline: bool = False,
    ):
        if isinstance(assignment, int):
            assignment = Assignment.objects.get(pk=assignment)
        if assignment.submission_type != AssignmentFormat.JBA:
            raise ValueError('Assignment type is not JBA')
        if not assignment.jba_course_id:
            raise ValueError('jba_course_id is not set')

        jba_course = JbaService._client.get_course(assignment.jba_course_id)
        if not jba_course:
            raise ValueError('JBA course not found')
        jba_course_tasks = [x for x in jba_course.tasks if x.type != 'theory']
        jba_course_tasks_ids = {x.id for x in jba_course_tasks}

        q = StudentAssignment.objects.filter(assignment=assignment)
        if user_ids:
            q = q.filter(student__pk__in=user_ids)
        student_assignments = {
            x.student.jetbrains_account: x for x in q.select_related('student')
        }

        should_update_score = timezone.now() <= assignment.deadline_at or at_deadline

        progress = JbaService._client.get_course_progress(
            jba_course.id, list(student_assignments.keys())
        )
        for jba_email, solved_task_ids in progress.items():
            sa = student_assignments[jba_email]
            solved_task_ids = sorted(
                x for x in solved_task_ids if x in jba_course_tasks_ids
            )
            last_comment = (
                AssignmentComment.published.filter(student_assignment=sa)
                .order_by('-created')
                .first()
            )
            if (
                last_comment
                and last_comment.meta.get('jba_solved_task_ids') == solved_task_ids
            ):
                continue

            with transaction.atomic():
                message = JbaService._generate_comment(
                    jba_course_tasks, solved_task_ids
                )
                if should_update_score:
                    new_score = (
                        Decimal(len(solved_task_ids))
                        / len(jba_course_tasks)
                        * assignment.maximum_score
                    )
                    new_score = round(new_score, 2)
                    # Creates a comment and updates the score
                    comment = create_personal_assignment_review(
                        student_assignment=sa,
                        reviewer=None,
                        is_draft=False,
                        score_old=sa.score,
                        score_new=new_score,
                        status_old=sa.status,
                        status_new=AssignmentStatus.COMPLETED,
                        source=AssignmentScoreUpdateSource.JBA_SUBMISSION,
                        message=message,
                        jba_solved_task_ids=solved_task_ids,
                    )
                    if at_deadline:
                        comment.created = assignment.deadline_at
                        comment.save()
                else:
                    create_assignment_comment(
                        personal_assignment=sa,
                        created_by=None,
                        is_draft=False,
                        message=message,
                        meta={'jba_solved_task_ids': solved_task_ids},
                    )

    @staticmethod
    def update_current_assignments_progress():
        assignments = Assignment.objects.filter(
            submission_type=AssignmentFormat.JBA
        ).with_future_deadline()
        for assignment in assignments:
            JbaService.update_assignment_progress(assignment)

        JbaService.schedule_update_current_assignments_progress()

    @staticmethod
    def schedule_update_current_assignments_progress():
        queue = get_queue('default')
        queue.enqueue_in(
            timedelta(minutes=settings.SUBMISSION_SERVICE_REFRESH_INTERVAL_MINUTES),
            JbaService.update_current_assignments_progress,
            job_id='update_jba_progress',
        )
