export default function launch() {
  $('.has-popover')
    .popover({
      container: 'body',
      html: true,
      placement: 'auto',
      trigger: 'hover click',
      content: function () {
        let helpBlockId = $(this).data('target');
        return $(helpBlockId).html();
      }
    })
    .on('show.bs.popover', function () {
      $(this).data('bs.popover').tip().css('max-width', '800px');
    });

  $('select[name="assignment-assignee_mode"]').change(function (e) {
    const mode = this.value || null;
    updateAssigneeModeAdditionSettings(mode);
  });

  updateMarketplaceIdVisibility()
  $('#id_assignment-submission_type').change(updateMarketplaceIdVisibility)
}

function updateMarketplaceIdVisibility() {
  const marketplaceFieldWrapper = $('#marketplace-field-wrapper')
  const submissionTypeSelect = $('#id_assignment-submission_type')
  const submissionType = submissionTypeSelect.val()
  if (submissionType === 'jba') {
    marketplaceFieldWrapper.removeClass('hidden')
  } else {
    marketplaceFieldWrapper.addClass('hidden')
  }
}

function updateAssigneeModeAdditionSettings(mode) {
  $('div[data-assignee-mode]').addClass('hidden');
  if (mode !== null) {
    const modeFormWrapper = $(`div[data-assignee-mode="${mode}"]`);
    modeFormWrapper.removeClass('hidden');
    if (mode !== 'sg_custom') {
      modeFormWrapper.find('input[required=true]').removeAttr('required');
    }
  }
}

let addButton = document.querySelector("#add-form");
let bucketsContainer = document.querySelector("#buckets-formset")
let emptyForm = document.querySelector("#buckets-empty-form").firstElementChild
let totalFormsInput = document.querySelector("#id_bucket-TOTAL_FORMS");

addButton.addEventListener('click', addBucket);
for (let formIndex=0; formIndex < totalFormsInput.value; formIndex++) {
    connectClearFillButtons(`bucket-${formIndex}`)
}

function connectClearFillButtons(formPrefix) {
  let fillSG = document.querySelector(`#id_${formPrefix}-FILL-SG`)
  let clearSG = document.querySelector(`#id_${formPrefix}-CLEAR-SG`)
  let fillCT = document.querySelector(`#id_${formPrefix}-FILL-CT`)
  let clearCT = document.querySelector(`#id_${formPrefix}-CLEAR-CT`)
  fillSG.addEventListener('click', (e) => {
    let sg_select = document.querySelector(`#id_${formPrefix}-student_groups`)
    for (let opt of sg_select.options) {
      opt.selected = 'selected';
    }
    sg_select.dispatchEvent(new Event('change'));
  })
  clearSG.addEventListener('click', (e) => {
    let sg_select = document.querySelector(`#id_${formPrefix}-student_groups`)
    for (let opt of sg_select.options) {
      opt.selected = '';
    }
    sg_select.dispatchEvent(new Event('change'));
  })
  fillCT.addEventListener('click', (e) => {
    let ct_select = document.querySelector(`#id_${formPrefix}-teachers`)
    for (let opt of ct_select.options) {
      opt.selected = 'selected';
    }
    ct_select.dispatchEvent(new Event('change'));
  })
  clearCT.addEventListener('click', (e) => {
    let ct_select = document.querySelector(`#id_${formPrefix}-teachers`)
    for (let opt of ct_select.options) {
      opt.selected = '';
    }
    ct_select.dispatchEvent(new Event('change'));
  })

}

function addBucket(event) {
  event.preventDefault();

  let totalFormsNum = totalFormsInput.value - 1;
  let newForm = emptyForm.cloneNode(true);
  let formRegex = RegExp(`__prefix__`,'g');
  totalFormsNum++;
  newForm.innerHTML = newForm.innerHTML.replace(formRegex, totalFormsNum);
  bucketsContainer.appendChild(newForm);
  totalFormsInput.setAttribute('value', totalFormsNum + 1);
  connectClearFillButtons(`bucket-${totalFormsNum}`)
}
