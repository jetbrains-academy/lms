from typing import Optional

from core.urls import reverse
from courses.constants import AssignmentFormat
from courses.models import Semester
from learning.forms import (AssignmentSolutionBaseForm, AssignmentSolutionDefaultForm)
from learning.models import AssignmentComment, StudentAssignment, Enrollment
from learning.services.personal_assignment_service import (create_assignment_solution)
from users.models import User


def get_solution_form(student_assignment: StudentAssignment,
                      data=None, files=None) -> Optional[AssignmentSolutionBaseForm]:
    assignment = student_assignment.assignment
    assignment_format = assignment.submission_type
    if assignment_format in (
        AssignmentFormat.NO_SUBMIT,
        AssignmentFormat.PENALTY,
        AssignmentFormat.JBA
    ):
        return None
    elif assignment_format == AssignmentFormat.EXTERNAL:
        # FIXME: return None
        form = AssignmentSolutionDefaultForm(assignment, data=data, files=files)
    else:
        form = AssignmentSolutionDefaultForm(assignment, data=data, files=files)
    if form:
        add_solution_url = reverse('study:assignment_solution_create',
                                   kwargs={'pk': student_assignment.pk})
        form.helper.form_action = add_solution_url
    return form


def save_solution_form(*, form: AssignmentSolutionBaseForm,
                       personal_assignment: StudentAssignment,
                       created_by: User) -> AssignmentComment:
    if isinstance(form, AssignmentSolutionDefaultForm):
        solution_data = {
            "message": form.cleaned_data['text'],
            "attachment": form.cleaned_data['attached_file'],
            "execution_time": form.cleaned_data['execution_time'],
        }
        submission = create_assignment_solution(
            personal_assignment=personal_assignment,
            created_by=created_by,
            **solution_data)
    else:
        raise ValueError(f"{form.__class__} is not supported")
    return submission


def get_current_semester_active_courses(student: User, current_term: Semester):
    return (Enrollment.active
            .filter(course__semester=current_term, student=student)
            .values_list("course", flat=True))
