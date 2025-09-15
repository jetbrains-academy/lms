import { ru } from 'date-fns/locale';
import ky from 'ky';

import { createNotification } from 'utils';

import { parseAssignments, parsePersonalAssignments } from './utils';

export const fetchData = async (
  { csrfToken, timeZone, updateState, initialState, queryParams },
  controller
) => {
  const searchParams = {
    course: queryParams.course || initialState.course,
    assignments: queryParams.assignments || initialState.selectedAssignments
  };
  return Promise.all([
    fetchCourseSettings([csrfToken, searchParams.course], controller),
    fetchPersonalAssignments([csrfToken, timeZone, updateState, searchParams], controller)
  ])
    .then(responses => {
      const [[assignmentsJSON, enrollmentsJSON], personalAssignmentsJSON] = responses;
      const assignments = parseAssignments({
        items: assignmentsJSON,
        timeZone,
        locale: ru
      });
      const assignmentOptions = [];
      assignments.forEach((assignment, key) => {
        assignmentOptions.push({
          value: assignment.id,
          label: assignment.title
        });
      });
      const studentGroups = new Map();
      enrollmentsJSON.forEach(item => {
        studentGroups.set(item.student.id, item.studentGroupId);
      });
      const personalAssignments = parsePersonalAssignments({
        items: personalAssignmentsJSON,
        studentGroups,
        timeZone,
        locale: ru
      });
      updateState({
        isInitialized: true,
        assignments,
        assignmentOptions, // TODO: useMemo instead
        studentGroups,
        personalAssignments
      });
    })
    .catch(error => {
      console.debug(error);
      createNotification('Something went wrong.', 'error');
    });
};

const fetchCourseSettings = async ([csrfToken, course], { signal }) => {
  const assignments = ky
    .get(`/api/v1/teaching/courses/${course}/assignments/`, {
      headers: {
        'X-CSRFToken': csrfToken
      },
      throwHttpErrors: false,
      signal: signal
    })
    .then(async response => {
      if (!response.ok) {
        return Promise.reject(new Error('fail'));
      }
      return response.json();
    });
  const enrollments = ky
    .get(`/api/v1/teaching/courses/${course}/enrollments/`, {
      headers: {
        'X-CSRFToken': csrfToken
      },
      throwHttpErrors: false,
      signal: signal
    })
    .then(async response => {
      if (!response.ok) {
        return Promise.reject(new Error('fail'));
      }
      return response.json();
    });
  return Promise.all([assignments, enrollments]);
};

const fetchPersonalAssignments = async (
  [csrfToken, timeZone, updateState, searchParams],
  { signal }
) => {
  return ky
    .get(`/api/v1/teaching/courses/${searchParams.course}/personal-assignments/`, {
      headers: {
        'X-CSRFToken': csrfToken
      },
      searchParams: { assignments: searchParams.assignments },
      throwHttpErrors: false,
      signal: signal
    })
    .then(async response => {
      if (!response.ok) {
        return Promise.reject(new Error('fail'));
      }
      return response.json();
    });
};

export const refetchPersonalAssignments = async (
  [csrfToken, timeZone, updateState, studentGroups, searchParams],
  controller
) => {
  fetchPersonalAssignments([csrfToken, timeZone, updateState, searchParams], controller)
    .then(data => {
      const personalAssignments = parsePersonalAssignments({
        items: data,
        studentGroups,
        timeZone,
        locale: ru
      });
      updateState({ personalAssignments });
    })
    .catch(error => {
      if (error.name === 'AbortError') {
        console.debug('Abort fetch');
      } else {
        console.debug(error);
        createNotification('Something went wrong.', 'error');
      }
    });
};
