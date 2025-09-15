$(() => {
  const isForAlumniCheckbox = $('#id_is_for_alumni')
  const alumniEnrollmentEndDateWrapper = $('.field-alumni_enrollment_end_date')

  function updateVisibility() {
    alumniEnrollmentEndDateWrapper.toggle(isForAlumniCheckbox.is(':checked'))
  }

  isForAlumniCheckbox.on('change', updateVisibility)
  updateVisibility()
})
