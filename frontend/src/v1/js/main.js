import 'bootstrap-sass';
import $ from 'jquery';
import 'jgrowl/jquery.jgrowl.js';
import 'bootstrap-select/js/bootstrap-select';
import 'jasny-bootstrap/js/fileinput';

import 'mathjax_config';
import UberEditor from 'components/editor';
import { csrfSafeMethod, getCSRFToken, getSections, showComponentError, loadReactApplications, createNotification } from './utils';
import hljs from 'highlight.js'

const CSC = window.__CSC__;

$(document).ready(function () {
  configureCSRFAjax();
  displayNotifications();
  renderText();
  initUberEditors();
  initCollapsiblePanelGroups();
  setupFileInputs();

  let sections = getSections();
  if (sections.includes('datetimepickers')) {
    import('components/forms')
      .then(m => {
        m.initDatePickers();
        m.initTimePickers();
      })
      .catch(error => showComponentError(error));
  }
  if (sections.includes('selectpickers')) {
    import('components/forms')
      .then(m => {
        m.initSelectPickers();
      })
      .catch(error => showComponentError(error));
  }
  if (sections.includes('lazy-img')) {
    import(/* webpackChunkName: "lazyload" */ 'components/lazyload')
      .then(m => m.launch())
      .catch(error => showComponentError(error));
  }
  // FIXME: combine into one peace `courses`?
  if (sections.includes('courseDetails')) {
    import(/* webpackChunkName: "courseDetails" */ 'courses/courseDetails')
      .then(m => m.launch())
      .catch(error => showComponentError(error));
  }
  if (sections.includes('courseOfferings')) {
    import(/* webpackChunkName: "courseOfferings" */ 'courses/courseOfferings')
      .then(m => m.launch())
      .catch(error => showComponentError(error));
  }
  if (sections.includes('profile')) {
    import(/* webpackChunkName: "profile" */ 'users/profile')
      .then(m => m.launch())
      .catch(error => showComponentError(error));
  }
  if (sections.includes('learning/solution')) {
    import(/* webpackChunkName: "solution" */ 'learning/solution')
      .then(m => m.launch())
      .catch(error => showComponentError(error));
  }

  loadReactApplications();
});

function displayNotifications() {
  if (window.__CSC__.notifications !== undefined) {
    window.__CSC__.notifications.forEach(message => {
      $.jGrowl(message.text, {
        position: 'bottom-right',
        sticky: message.timeout !== 0,
        theme: message.type
      });
    });
  }
}

function configureCSRFAjax() {
  // Append csrf token on ajax POST requests made with jQuery
  // FIXME: add support for allowed subdomains
  $.ajaxSetup({
    beforeSend: function (xhr, settings) {
      if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
        xhr.setRequestHeader('X-CSRFToken', getCSRFToken());
      }
    }
  });
}

function renderText() {
  // highlight js and MathJax
  const $ubertexts = $('div.ubertext');
  // Note: MathJax and hljs loads for each iframe separately
  if ($ubertexts.length > 0) {
    UberEditor.preload(function () {
      // Configure highlight js
      hljs.configure({ tabReplace: '    ' });
      // Render Latex and highlight code
      $ubertexts.each(function (i, target) {
        UberEditor.render(target);
      });
    });
  }
}

function initUberEditors() {
  // Replace textarea with EpicEditor
  const $ubereditors = $('textarea.ubereditor');
  UberEditor.cleanLocalStorage($ubereditors);
  $ubereditors.each(function (i, textarea) {
    const editor = UberEditor.init(textarea);
    CSC.config.uberEditors.push(editor);
  });
  if ($ubereditors.length > 0) {
    $('a[data-toggle="tab"]').on('shown.bs.tab', UberEditor.reflowOnTabToggle);
  }
}

function initCollapsiblePanelGroups() {
  $('.panel-group').on('click', '.panel-heading._arrowed', function (e) {
    // Replace js animation with css.
    e.preventDefault();
    const open = $(this).attr('aria-expanded') === 'true';
    $(this).next().toggleClass('collapse').attr('aria-expanded', !open);
    $(this).attr('aria-expanded', !open);
  });
}

function setupFileInputs() {
  $('.jasny.fileinput')
    .on('clear.bs.fileinput', function (event) {
      $(event.target).find('.fileinput-clear-checkbox').val('on');
      $(event.target).find('.fileinput-filename').text('No file selected');
    })
    .on('change.bs.fileinput', function (event) {
      $(event.target).find('.fileinput-clear-checkbox').val('');
    })
    .on('reseted.bs.fileinput', function (event) {
      $(event.target).find('.fileinput-filename').text('No file selected');
      $(event.target).find('.fileinput-clear-checkbox').val('on');
    });
  const fileInputs = document.querySelectorAll('.jasny.fileinput input[type="file"]')
  const maxUploadSize = window.__CSC__.config.maxUploadSize
  const maxUploadSizeStr = maxUploadSize / 1024 / 1024 + ' MiB'
  fileInputs.forEach(fileInput => {
    fileInput.addEventListener('change', e => {
      for (const file of e.target.files) {
        if (file.size > maxUploadSize) {
          createNotification('Cannot upload files larger than ' + maxUploadSizeStr, 'error')
          e.target.value = null
        }
      }
    })
  })
}
