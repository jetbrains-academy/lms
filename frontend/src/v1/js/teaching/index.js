import { showComponentError, getSections } from 'utils';

$(document).ready(function () {
  let sections = getSections();
  if (sections.includes('tooltips')) {
    let defaultWhiteList = $.fn.tooltip.Constructor.DEFAULTS.whiteList;
    defaultWhiteList.dl = ['class'];
    defaultWhiteList.dd = [];
    defaultWhiteList.dt = [];
    $('[data-toggle="tooltip"]').tooltip();
  }
  if (sections.includes('studentAssignment')) {
    import(/* webpackChunkName: "gradebook" */ 'teaching/studentAssignment')
      .then(module => {
        const component = module.default;
        component.launch();
      })
      .catch(error => showComponentError(error));
  } else if (sections.includes('studentGroups')) {
    import(/* webpackChunkName: "studentGroups" */ 'teaching/studentGroups')
      .then(module => {
        const launch = module.default;
        launch();
      })
      .catch(error => showComponentError(error));
  }

  if (sections.includes('gradebook')) {
    import(/* webpackChunkName: "gradebook" */ 'teaching/gradebook')
      .then(module => {
        const component = module.default;
        component.launch();
      })
      .catch(error => showComponentError(error));
  } else if (sections.includes('submissions')) {
    import(/* webpackChunkName: "submissions" */ 'teaching/submissions')
      .then(m => {
        const component = m.default;
        component.launch();
      })
      .catch(error => showComponentError(error));
  } else if (sections.includes('assignmentForm')) {
    import(/* webpackChunkName: "assignmentForm" */ 'teaching/assignmentForm')
      .then(m => {
        m.default();
      })
      .catch(error => showComponentError(error));
  }
});
