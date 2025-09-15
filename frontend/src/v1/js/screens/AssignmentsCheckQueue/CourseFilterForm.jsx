// TODO: refactor using the Select component
import React, { useState, useEffect, useRef } from 'react';
import PropTypes from 'prop-types';
import ky from 'ky';
import _xor from 'lodash-es/xor';
import 'bootstrap-select/js/bootstrap-select';
import 'bootstrap-select/js/i18n/defaults-en_US';
import { parseAssignments } from './utils';

const onCourseChange = async (
  course,
  timeZone,
  assignmentsSelectRef,
  setCourse,
  setAssignments
) => {
  const endpoint = `/api/v1/teaching/courses/${course}/assignments/`;

  const response = await ky.get(endpoint);
  const assignmentsSelect = $(assignmentsSelectRef.current);
  const data = await response.json();
  const assignments = parseAssignments({ items: data, timeZone });
  const options = [];
  assignments.forEach(item => {
    options.push(
      $('<option>', {
        text: item.title,
        value: item.id
      })
    );
  });
  assignmentsSelect.empty().append(options);
  assignmentsSelect.attr('disabled', options.length === 0);
  setCourse(course);
  setAssignments([]);
};

const CourseFilterForm = ({
  timeZone,
  courseOptions,
  assignmentOptions,
  selectedCourse,
  selectedAssignments,
  onSubmitForm
}) => {
  const assignmentsSelectRef = useRef(null);
  const [course, setCourse] = useState(selectedCourse);
  const [assignments, setAssignments] = useState(selectedAssignments);
  const filterButtonDisabled =
    assignments.length === 0 ||
    _xor(assignments, selectedAssignments).length === 0;

  useEffect(() => {
    $('select[name=assignments], select[name=course]').selectpicker({
      iconBase: 'fa',
      tickIcon: 'fa-check'
    });
  }, []);

  useEffect(() => {
    $('select[name=assignments]').selectpicker('refresh');
  });

  useEffect(() => {
    if (assignments !== selectedAssignments) {
      setAssignments(selectedAssignments);
    }
    // Omit `assignments` in useEffect dependencies since we want to sync
    // control component state on props.selectedAssignments change only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setAssignments, selectedAssignments]);

  const handleSubmitForm = e => {
    e.preventDefault();
    onSubmitForm({
      course: parseInt(course, 10),
      assignments
    });
  };

  return (
    <form
      action=""
      className="mb-30"
      id="assignment-filters"
      onSubmit={handleSubmitForm}
    >
      <div className="row">
        <div className="col-xs-4">
          <div className="form-group">
            <label htmlFor="id_course" className="control-label">
              Course reading
            </label>
            <div className="controls">
              <select
                name="course"
                className="select form-control my-picker"
                id="id_course"
                value={course}
                onChange={e => {
                  onCourseChange(
                    e.target.value,
                    timeZone,
                    assignmentsSelectRef,
                    setCourse,
                    setAssignments
                  );
                }}
              >
                {courseOptions.map(option => (
                  <option key={`course-${option.value}`} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
        <div className="col-xs-5">
          <div className="form-group">
            <label htmlFor="id_assignment" className="control-label">
              Assignments
            </label>
            <div className="controls">
              <select
                ref={assignmentsSelectRef}
                name="assignments"
                className="select form-control my-picker"
                id="id_assignment"
                multiple
                size="1"
                value={assignments}
                disabled={assignmentOptions.length === 0}
                onChange={e => {
                  const selectedValues = $(assignmentsSelectRef.current)
                    .val()
                    .map(v => parseInt(v));
                  setAssignments(selectedValues);
                }}
                data-selected-text-format="count > 1"
              >
                {assignmentOptions.map(option => (
                  <option
                    key={`assignment-${option.value}`}
                    value={option.value}
                  >
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <div className="col-xs-3">
          <button
            type="submit"
            className="btn btn-primary btn-block -inline-submit"
            disabled={filterButtonDisabled}
          >
            Apply
          </button>
        </div>
      </div>
    </form>
  );
};

CourseFilterForm.propTypes = {
  timeZone: PropTypes.string.isRequired,
  courseOptions: PropTypes.arrayOf(
    PropTypes.shape({
      value: PropTypes.number.isRequired,
      label: PropTypes.string.isRequired
    })
  ).isRequired,
  assignmentOptions: PropTypes.arrayOf(
    PropTypes.shape({
      value: PropTypes.number.isRequired,
      label: PropTypes.string.isRequired
    })
  ).isRequired,
  selectedCourse: PropTypes.number.isRequired,
  selectedAssignments: PropTypes.arrayOf(PropTypes.number).isRequired,
  onSubmitForm: PropTypes.func.isRequired
};

export default CourseFilterForm;
