import { getTemplate, showComponentError } from 'utils';
import { createNotification } from '../utils';
import { FormValidation } from 'components/formValidator';
import { format } from 'date-fns/fp';
import { utcToZonedTime } from 'date-fns-tz';

function initAssignmentScoreAuditLog() {
  $('.assignment-score-audit-log').click(function (e) {
    e.preventDefault();
    const modalWrapper = $('#modal-container');
    const template = getTemplate('assignment-score-audit-log-table');
    $.get(this.href, function (data) {
      const header = 'Assignment grade change history';
      $('.modal-dialog', modalWrapper).addClass('modal-lg');
      $('.modal-header', modalWrapper).html(
        `${header} <button type="button" class="close" data-dismiss="modal" aria-hidden="true">×</button>`
      );
      const dateToString = format('LLL d, yyyy HH:mm');
      const timeZone = window.__CSC__?.profile?.timezone || 'UTC';
      data.edges.forEach(node => {
        const editor = node.changedBy ?? {firstName: 'System', lastName: ''};
        const fullName = `${editor.lastName} ${editor.firstName}`.trim();
        node.author = fullName || editor.username;
        node.source = data.sources[node.source];
        const created = new Date(node.createdAt);
        const zonedDate = utcToZonedTime(created, timeZone);
        node.createdAt = dateToString(zonedDate);
      });
      const html = template({ edges: data.edges });
      $('.modal-body', modalWrapper).html(html);
      modalWrapper.modal('show');
    }).fail(data => {
      if (data.status === 403) {
        createNotification('Access denied', 'error');
        $(this).remove();
      }
    });
  });
}

function initAssigneeForm() {
  const modalFormWrapper = $('#update-assignee-form');
  modalFormWrapper.modal({
    show: false
  });

  new FormValidation(
    modalFormWrapper.find('form').get(0),
    function (form, data) {
      let assigneeId = data.assignee;
      if (assigneeId === null) {
        assigneeId = '';
      }
      const selectedAssigneeOption = form.querySelector(
        `select[name="assignee"] option[value="${assigneeId}"]`
      );
      $('#assignee-value').text(selectedAssigneeOption.text);
      createNotification('Changes saved successfully');
      modalFormWrapper.modal('hide');
    },
    function () {
      createNotification('Error saving form', 'error');
    }
  );
  modalFormWrapper.on('submit', 'form', function (e) {
    e.preventDefault();
    const form = e.target;
    const assigneeSelect = document.querySelector('#assignee-select');
    const assigneeId = assigneeSelect.value;
    const assigneeName = assigneeSelect.options[assigneeSelect.selectedIndex].text;
    $.ajax({
      method: 'PUT',
      url: form.getAttribute('action'),
      dataType: 'json',
      data: {
        assignee: assigneeId
      }
    })
      .done(data => {
        $('#assignee-value').text(assigneeName);
      })
      .fail(xhr => {
        createNotification('Something went wrong.', 'error');
        console.log(xhr);
      });
  });
}

const fn = {
  launch: function () {
    initAssigneeForm();
    import('components/forms')
      .then(m => {
        m.initSelectPickers();
      })
      .catch(error => showComponentError(error));
    initAssignmentScoreAuditLog();
  }
};

export default fn;
