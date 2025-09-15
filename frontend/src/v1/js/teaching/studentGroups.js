export default function launch() {
  const form = window.document.querySelector('form[name="transfer-students"]');
  if (form !== null) {
    form.addEventListener('submit', e => {
      const studentProfiles = form.querySelectorAll('input[name="ids"]');
      const hasCheckedStudentProfiles = Array.from(studentProfiles).some(el => el.checked);
      if (!hasCheckedStudentProfiles) {
        e.preventDefault();
      }
    });
  }
}
