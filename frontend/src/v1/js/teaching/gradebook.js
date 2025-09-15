import { createNotification } from 'utils';
import _throttle from 'lodash-es/throttle';

const buttonDownloadCSV = $('.marks-sheet-csv-link');
let submitButton = $('#marks-sheet-save');
let gradebookContainer = $('#gradebook-container');
let gradebook = $('#gradebook');
let scrollButtonsWrapper = $('.gradebook__controls');

function isChanged(element) {
  return element.value !== element.getAttribute('initial');
}

const fn = {
  launch: function () {
    fn.restoreStates();
    fn.finalGradeSelects();
    fn.submitForm();
    fn.downloadCSVButton();
    fn.onChangeAssignmentGrade();
    fn.scrollButtons();
    fn.importYandexContestProblemForm();
  },

  /**
   * If browser supports html5 `autocomplete` attribute,
   * we can accidentally hide unsaved state on page reload.
   */
  restoreStates: function () {
    let inputs = document.querySelectorAll('#gradebook .__input');
    Array.prototype.forEach.call(inputs, fn.toggleState);
    let selects = document.querySelectorAll('#gradebook select');
    Array.prototype.forEach.call(selects, fn.toggleState);
  },

  downloadCSVButton: function () {
    buttonDownloadCSV.click(function () {
      if (gradebook.find('.__unsaved').length > 0) {
        createNotification('To download latest data save the form first.', 'warning');
        return false;
      }
    });
  },

  submitForm: function () {
    submitButton.click(function () {
      $('form[name=gradebook]').submit();
    });

    // Form heavily relies on js-behavior. `Disabled` default state
    // prevents accidental submission if js is not activated.
    // submitButton.removeAttr("disabled");
    $('form[name=gradebook]').submit(function (e) {
      let elements = this.querySelectorAll('.__input, .__final_grade select');
      Array.prototype.forEach.call(elements, function (element) {
        if (!isChanged(element)) {
          element.disabled = true;
          const inputQuery = `input[name=initial-${element.name}]`;
          document.querySelector(inputQuery).disabled = true;
        }
      });
    });
  },

  finalGradeSelects: function () {
    gradebook.on('change', 'select', function (e) {
      fn.toggleState(e.target);
    });
  },

  onChangeAssignmentGrade: function () {
    gradebook.on('change', 'input.__assignment', function (e) {
      fn.toggleState(e.target);
    });
  },

  toggleState: function (element) {
    let wrapper;
    if (element.nodeName.toLowerCase() === 'input') {
      wrapper = element;
    } else if (element.nodeName.toLowerCase() === 'select') {
      wrapper = element.parentElement;
    }
    if (isChanged(element)) {
      wrapper.classList.add('__unsaved');
    } else {
      wrapper.classList.remove('__unsaved');
    }
  },

  scrollButtons: function () {
    if (gradebookContainer.width() <= gradebook.outerWidth()) {
      scrollButtonsWrapper.on('click', '.scroll.left', function () {
        fn.scroll(-1);
      });
      scrollButtonsWrapper.on('click', '.scroll.right', function () {
        fn.scroll(1);
      });
      scrollButtonsWrapper.css('visibility', 'visible');
    }
  },

  scroll: function (xdir) {
    const assignmentColumnWidth = 100;
    const xinc = assignmentColumnWidth * parseInt(xdir);
    if (xinc !== 0) {
      const scrollXOffset = gradebookContainer.scrollLeft();
      gradebookContainer.scrollLeft(scrollXOffset + xinc);
    }
  },

  importYandexContestProblemForm: function () {
    const throttledHandleSubmit = _throttle(handleSubmit, 1000, { leading: true, trailing: false });
    function handleSubmit(url, assignmentId) {
      $.ajax({
        method: 'POST',
        url: url,
        dataType: 'json',
        data: {
          assignment: assignmentId
        }
      })
        .done(data => {
          createNotification('Import finished, the page will be reloaded', 'info');
          setTimeout(() => window.location.reload(), 500);
        })
        .fail(xhr => {
          let message;
          if (xhr.responseJSON && xhr.responseJSON.errors !== undefined) {
            const messages = xhr.responseJSON.errors.map(error => error.message);
            message = messages.join('<br/>');
          } else {
            message = `${xhr.statusText}. Try again later.`;
          }
          if (xhr.status >= 500 && xhr.status < 600) {
            createNotification(message, 'error', { sticky: true });
          } else {
            createNotification(message, 'error');
          }
        });
    }

    const modalWrapper = $('#import-scores-from-yandex-contest');
    modalWrapper.on('submit', 'form', function (e) {
      e.preventDefault();
      const form = e.target;
      const assignmentId = form.querySelector('select[name=assignment]').value || null;
      if (assignmentId === null) {
        return;
      }
      throttledHandleSubmit(form.getAttribute('action'), assignmentId);
      modalWrapper.modal('hide');
    });
  }
};

export default fn;
