import PropTypes from 'prop-types';
import React, {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useState
} from 'react';

import cn from 'classnames';
import countBy from 'lodash-es/countBy';
import isEqual from 'lodash-es/isEqual';
import { useAsync } from 'react-async';
import {
  Route,
  BrowserRouter as Router,
  Routes,
  useNavigate
} from 'react-router-dom';

import Checkbox from '../../components/Checkbox';
import CheckboxButton from '../../components/CheckboxButton';
import CourseFilterForm from './CourseFilterForm';
import { fetchData, refetchPersonalAssignments } from './fetch';
import PersonalAssignmentList from './PersonalAssignmentList';
import {
  FiltersURLSearchParams,
  getFilteredPersonalAssignments,
  scoreOptions,
  sortEnum,
  sortOptions,
  sortPersonalAssignments,
  stateReducer,
  useFilterState,
  useQueryParams
} from './utils';

function AssignmentsCheckQueue({
  csrfToken,
  timeZone,
  statusOptions,
  courseOptions,
  courseTeachers,
  courseGroups,
  initialState
}) {
  const queryParams = useQueryParams();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [state, updateState] = useReducer(stateReducer, {
    isInitialized: false,
    assignments: new Map(),
    assignmentOptions: [],
    personalAssignments: null,
    studentGroups: null
  });
  const { counter: fetchCounter, run } = useAsync({
    promiseFn: fetchData,
    deferFn: refetchPersonalAssignments,
    csrfToken,
    timeZone,
    queryParams,
    initialState,
    updateState
  });
  const [filters, setFilters, onFilterChange] = useFilterState({
    course: initialState.course,
    assignments: initialState.selectedAssignments,
    statuses: queryParams.statuses || [],
    score: queryParams.score || [],
    reviewers: queryParams.reviewers || [],
    studentGroups: queryParams.studentGroups || [],
    sort: queryParams.sort || sortEnum.SOLUTION_ASC
  });
  console.debug('filters on render', filters);

  const { assignments, assignmentOptions, studentGroups, personalAssignments } =
    state;

  const handleSubmitForm = ({ course, assignments }) => {
    const filterURLSearchParams = new FiltersURLSearchParams();
    filterURLSearchParams.assign({
      course,
      assignments,
      score: filters.score,
      sort: filters.sort
      // TODO: filters.statuses?
    });

    // In case of changing course value we should fetch new student groups
    // As a workaround let's reload the page
    if (filterURLSearchParams.course !== filters.course) {
      window.location.href = filterURLSearchParams.toString();
      return;
    }
    console.debug('navigate()', filterURLSearchParams);
    navigate(window.location.pathname + filterURLSearchParams.toString());
  };

  // history.listen() callback
  useEffect(() => {
    console.debug(`Eval history.listen() triggered: ${!state.isInitialized}`);
    if (!state.isInitialized) {
      return;
    }

    const filtersPrevious = filters;
    const filtersNext = Object.assign({}, filtersPrevious, {
      course: queryParams.course || initialState.course,
      assignments: queryParams.assignments || initialState.selectedAssignments,
      statuses: queryParams.statuses || [],
      score: queryParams.score || [],
      studentGroups: queryParams.studentGroups || [],
      reviewers: queryParams.reviewers || [],
      sort: queryParams.sort || sortEnum.SOLUTION_ASC
    });

    if (!isEqual(filtersPrevious, filtersNext)) {
      setFilters(filtersNext);
    }
    // Refetch logic
    const formFiltersPrevious = {
      course: filtersPrevious.course,
      assignments: filtersPrevious.assignments
    };
    const formFiltersNext = {
      course: filtersNext.course,
      assignments: filtersNext.assignments
    };
    if (!isEqual(formFiltersPrevious, formFiltersNext)) {
      // TODO(perf): filter out personal assignments and update state instead of
      //  fetching if only some assignment checkboxes were removed
      console.debug('Fetch personal assignments');
      const filterURLSearchParams = new FiltersURLSearchParams();
      filterURLSearchParams.assign(filtersNext);
      run(
        csrfToken,
        timeZone,
        updateState,
        studentGroups,
        filterURLSearchParams
      );
      // Rerender multiple select in CourseFilterForm
      updateState({
        personalAssignments: null
      });
    }

    if (fetchCounter > 0) {
      setPage(1);
    }
    // XXX: Skip `state` to trigger callback on changing query parameters only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run, csrfToken, setPage, timeZone, updateState, queryParams]);

  const setFilterQueryParams = useCallback(
    newFilters => {
      const filterURLSearchParams = new FiltersURLSearchParams();
      filterURLSearchParams.assign(filters, newFilters);
      navigate(window.location.pathname + filterURLSearchParams.toString());
    },
    [filters, navigate]
  );

  const setFilterValues = useCallback(
    (name, value, checked) => {
      let values;
      values = filters[name] || [];
      if (checked) {
        values.push(value);
      } else {
        values = values.filter(v => v !== value);
      }

      setFilterQueryParams({
        [name]: values
      });
    },
    [filters, setFilterQueryParams]
  );

  const setStatusesFilter = useCallback(
    ({ value, checked }) => setFilterValues('statuses', value, checked),
    [setFilterValues]
  );

  const setScoreFilter = e =>
    setFilterValues('score', e.target.value, e.target.checked);

  const setReviewersFilter = e => {
    const value =
      e.target.value !== 'unset'
        ? parseInt(e.target.value, 10)
        : e.target.value;
    setFilterValues('reviewers', value, e.target.checked);
  };

  const setStudentGroupsFilter = e =>
    setFilterValues(
      'studentGroups',
      parseInt(e.target.value, 10),
      e.target.checked
    );

  const filteredPersonalAssignments = getFilteredPersonalAssignments(
    personalAssignments,
    filters
  );
  sortPersonalAssignments(filteredPersonalAssignments, filters.sort);

  const countByStatus = useMemo(
    () => countBy(personalAssignments, item => item.status),
    [personalAssignments]
  );
  const isLoaded = personalAssignments !== null;

  return (
    <>
      <CourseFilterForm
        timeZone={timeZone}
        courseOptions={courseOptions}
        assignmentOptions={assignmentOptions}
        selectedCourse={filters.course}
        selectedAssignments={filters.assignments}
        onSubmitForm={handleSubmitForm}
      />
      <h1 className="mb-20">Assignment queue</h1>
      <div className="row">
        <div className="col-xs-9">
          <div className="btn-group btn-group-sm mb-10">
            {statusOptions.map(option => {
              const total = countByStatus[option.value] || 0;
              const suffix = isLoaded ? ` (${total})` : '';
              return (
                <CheckboxButton
                  className="btn-default _checkbox"
                  key={`status-${option.value}`}
                  value={option.value}
                  checked={
                    !!filters.statuses &&
                    filters.statuses.includes(option.value)
                  }
                  onChange={setStatusesFilter}
                >
                  {`${option.label}${suffix}`}
                </CheckboxButton>
              );
            })}
          </div>
        </div>
      </div>
      <div className="row">
        <div className="col-xs-9 mb-5">
          <span className="text-muted">Sort by</span>:
          {sortOptions.map(option => {
            const active = filters.sort === option.value;
            return (
              <button
                onClick={_ => {
                  if (!active) {
                    setFilterQueryParams({ sort: option.value });
                  }
                }}
                className={cn({
                  'btn btn-link': true,
                  active
                })}
                key={`sort-${option.value}`}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      </div>
      <div className="row">
        <div className="col-xs-9">
          <PersonalAssignmentList
            page={page}
            setPage={setPage}
            isLoading={!isLoaded}
            assignments={assignments}
            statusOptions={statusOptions}
            items={filteredPersonalAssignments}
          />
        </div>

        <div className="col-xs-3">
          {studentGroups !== null && (
            <div className="mb-30">
              <h5 className="mt-0">Student group</h5>
              <>
                {courseGroups.map(option => (
                  <Checkbox
                    name="studentGroups"
                    key={`student-group-${option.value}`}
                    value={option.value}
                    checked={
                      !!filters.studentGroups &&
                      filters.studentGroups.includes(option.value)
                    }
                    onChange={setStudentGroupsFilter}
                    label={option.label}
                  />
                ))}
              </>
            </div>
          )}

          <div className="mb-30">
            <h5>Score</h5>
            {scoreOptions.map(option => (
              <Checkbox
                key={`score-${option.value}`}
                name="score"
                value={option.value}
                checked={
                  !!filters.score && filters.score.includes(option.value)
                }
                onChange={setScoreFilter}
                label={option.label}
              />
            ))}
          </div>

          <div className="mb-30">
            <h5>Reviewer</h5>
            <>
              {courseTeachers.map(option => (
                <Checkbox
                  key={`reviewer-${option.value}`}
                  name="reviewers"
                  value={option.value}
                  checked={
                    !!filters.reviewers &&
                    filters.reviewers.includes(option.value)
                  }
                  onChange={setReviewersFilter}
                  label={option.label}
                />
              ))}
            </>
          </div>
        </div>
      </div>
    </>
  );
}

AssignmentsCheckQueue.propTypes = {
  csrfToken: PropTypes.string.isRequired,
  timeZone: PropTypes.string.isRequired,
  initialState: PropTypes.shape({
    course: PropTypes.number.isRequired,
    selectedAssignments: PropTypes.arrayOf(PropTypes.number)
  }).isRequired,
  statusOptions: PropTypes.arrayOf(
    PropTypes.shape({
      value: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired
    })
  ).isRequired,
  courseOptions: PropTypes.arrayOf(
    PropTypes.shape({
      value: PropTypes.number.isRequired,
      label: PropTypes.string.isRequired
    })
  ).isRequired,
  courseTeachers: PropTypes.arrayOf(
    PropTypes.shape({
      value: PropTypes.oneOfType([PropTypes.number, PropTypes.string])
        .isRequired,
      label: PropTypes.string.isRequired,
      selected: PropTypes.bool.isRequired
    })
  ).isRequired,
  courseGroups: PropTypes.arrayOf(
    PropTypes.shape({
      value: PropTypes.number.isRequired,
      label: PropTypes.string.isRequired,
      selected: PropTypes.bool.isRequired
    })
  ).isRequired
};

export default function App(props) {
  return (
    <Router>
      <Routes>
        <Route
          path="/teaching/assignments/"
          element={<AssignmentsCheckQueue {...props} />}
        />
      </Routes>
    </Router>
  );
}
