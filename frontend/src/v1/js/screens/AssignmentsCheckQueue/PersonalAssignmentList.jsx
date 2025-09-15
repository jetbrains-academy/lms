import PropTypes from 'prop-types';
import React, { useMemo } from 'react';

import { formatDistance } from 'date-fns';
import ruLocale from 'date-fns/locale/ru';

import Pagination from 'components/Pagination';

import { getScoreClass } from './utils';

function formatScore(score) {
  if (score === null) {
    return '—';
  }
  const suffix = '.00';
  const index = score.indexOf(suffix, score.length - suffix.length);
  if (index === -1) {
    return score;
  } else {
    return score.substring(0, index);
  }
}

// TODO: calculate status label and assignment and pass in these values to the component (pros/cons?)
const PersonalAssignment = ({ data, assignments, statuses }) => {
  const { student, assignee, status, score, assignmentId, solutionAt } = data;
  const assignment = assignments.get(assignmentId);
  let studentFullName = `${student.lastName} ${student.firstName}`.trim();
  studentFullName = studentFullName || student.username;
  let assigneeFullName = '—';
  if (assignee !== null) {
    assigneeFullName =
      `${assignee.teacher.lastName} ${assignee.teacher.firstName}`.trim();
  }

  const solutionDistanceRelative =
    solutionAt !== null
      ? formatDistance(solutionAt, new Date(), {
          locale: ruLocale,
          addSuffix: true
        })
      : null;

  return (
    <tr>
      <td>
        <a href={`/teaching/assignments/submissions/${data.id}/`}>
          {studentFullName}
        </a>
      </td>
      <td>
        {statuses[status]}
        {solutionAt && (
          <>
            <br />
            <small className="text-muted">{solutionDistanceRelative}</small>
          </>
        )}
      </td>
      <td>
        <a href={`/teaching/assignments/${assignment.id}/`}>
          {assignment.title}
        </a>
        <br />
        <small className="text-muted">
          Deadline: {assignment.deadlineAtFormatted}
        </small>
      </td>
      <td>{assigneeFullName}</td>
      <td>
        <span className={`assignment-status ${getScoreClass(data.status)}`}>
          {formatScore(score)}/{assignment.maximumScore}
        </span>
      </td>
    </tr>
  );
};

PersonalAssignment.propTypes = {
  data: PropTypes.shape({
    id: PropTypes.number.isRequired,
    assignmentId: PropTypes.number.isRequired,
    student: PropTypes.shape({
      firstName: PropTypes.string.isRequired,
      lastName: PropTypes.string.isRequired,
      username: PropTypes.string.isRequired
    }).isRequired,
    assignee: PropTypes.shape({
      id: PropTypes.number.isRequired,
      teacher: PropTypes.shape({
        id: PropTypes.number.isRequired,
        firstName: PropTypes.string.isRequired,
        lastName: PropTypes.string.isRequired,
      }).isRequired
    }),
    solutionAt: PropTypes.instanceOf(Date),
    score: PropTypes.string,
    status: PropTypes.string.isRequired
  }),
  statuses: PropTypes.object.isRequired,
  assignments: PropTypes.objectOf(
    PropTypes.shape({
      id: PropTypes.number.isRequired,
      title: PropTypes.string.isRequired,
      maximumScore: PropTypes.number.isRequired,
      deadlineAt: PropTypes.string.isRequired,
      deadlineAtFormatted: PropTypes.string.isRequired
    })
  ).isRequired
};

const itemsPerPage = 50;

const PersonalAssignmentList = ({
  page,
  setPage,
  isLoading,
  assignments,
  statusOptions,
  items
}) => {
  const isShowPagination = items.length > itemsPerPage;
  const statuses = useMemo(
    () =>
      statusOptions.reduce((acc, option) => {
        acc[option.value] = option.label;
        return acc;
      }, {}),
    [statusOptions]
  );
  return (
    <>
      <div className="panel">
        <div className="panel-body">
          <table className="table mb-0">
            <thead>
              <tr>
                <th>Student</th>
                <th>Status</th>
                <th>Assignment</th>
                <th style={{ width: '60px' }}>Reviewer</th>
                <th style={{ width: '60px' }}>Score</th>
              </tr>
            </thead>
            <tbody>
              {!items.length && (
                <tr>
                  <td colSpan="5" className="empty-results">
                    {!isLoading &&
                      assignments.size > 0 &&
                      !items.length &&
                      'No results match the current filters'}
                    {!isLoading &&
                      !assignments.size &&
                      'The current course has no assignments'}
                  </td>
                </tr>
              )}
              {items.length > 0 &&
                items
                  .slice((page - 1) * itemsPerPage, page * itemsPerPage)
                  .map(item => (
                    <PersonalAssignment
                      key={`personal-assignment-${item.id}`}
                      data={item}
                      assignments={assignments}
                      statuses={statuses}
                    />
                  ))}
            </tbody>
          </table>
        </div>
      </div>
      {isShowPagination && (
        <Pagination
          totalItems={items.length}
          pageSize={itemsPerPage}
          currentPage={page}
          onChangePage={setPage}
          force={true}
        />
      )}
    </>
  );
};

PersonalAssignmentList.propTypes = {
  isLoading: PropTypes.bool.isRequired,
  items: PropTypes.arrayOf(PropTypes.object),
  assignments: PropTypes.objectOf(Map),
  statusOptions: PropTypes.arrayOf(
    PropTypes.shape({
      value: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired
    })
  ).isRequired,
  page: PropTypes.number.isRequired,
  setPage: PropTypes.func.isRequired
};

export default PersonalAssignmentList;
