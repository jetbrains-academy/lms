import _debounce from 'lodash-es/debounce'
import { escapeHTML } from 'utils'

const ENTRY_POINT = $('.user-search #ajax-uri').val();
const filters = {
  name: '',
  universities: {},
  academic_programs: {},
  year_of_admission: {},
  profile_types: {},
  status: {},
  cnt_enrollments: {},
  is_paid_basis: {},
};

function getSelectedValues(items) {
  return Object.keys(items)
    .filter(key => items[key])
    .join(',');
}

function makeQuery() {
  const payload = {};
  for (const [key, value] of Object.entries(filters)) {
    if (key == 'name') {
      payload[key] = value;
    } else {
      payload[key] = Object.keys(value)
        .filter(key => value[key])
        .join(',');
    }
  }

  $.ajax({
    url: ENTRY_POINT,
    data: payload,
    dataType: 'json',
    traditional: true
  })
    .done(function (data) {
      let found;
      if (data.next !== null) {
        found = `500 of ${data.count} results are shown`;
      } else {
        found = `${data.count} results`;
      }
      if (parseInt(data.count) > 0) {
        found += ` <a target="_blank" href="/staff/student-search.csv?${$.param(
          filters
        )}">download csv</a>`;
      }
      $('#user-num-container').html(found).show();
      let h = "<table class='table table-condensed'>";
      data.results.map(studentProfile => {
        h += `<tr><td>`;
        h += `<a href="/users/${studentProfile.user_id}/">${escapeHTML(studentProfile.short_name)}</a>`;
        h += '</td></tr>';
      });
      h += '</table>';
      $('#user-table-container').html(h);
    })
    .fail(function (jqXHR) {
      $('#user-num-container').html(`Request error`).show();
      $('#user-table-container').html(`<code>${jqXHR.responseText}</code>`);
    });
}

$(function () {
  const query = _debounce(makeQuery, 200);

  const userSearchForm = $('.user-search')
  userSearchForm.on('keydown', function (e) {
    // Supress Enter
    if (e.keyCode === 13) {
      e.preventDefault();
    }
  })
  for (const fieldName of Object.keys(filters)) {
    if (fieldName == 'name') {
      userSearchForm.on('input paste', `[name="${fieldName}"]`, function (e) {
        filters[fieldName] = $(this).val();
        query();
      });
    } else {
      userSearchForm.on('change', `[name="${fieldName}"]`, function (e) {
        filters[fieldName][$(this).val()] = this.checked;
        query();
      });
    }
  }
});
