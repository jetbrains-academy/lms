import 'bootstrap-select/js/bootstrap-select';
import 'bootstrap-select/js/i18n/defaults-en_US';
import { TempusDominus } from '@eonasdan/tempus-dominus'
import '~/scss/tempus-dominus.scss'

$.fn.selectpicker.Constructor.BootstrapVersion = '3';

export const TIMEPICKER_ICONS = {
  type: 'icons',
  time: 'fa fa-clock-o',
  date: 'fa fa-calendar',
  up: 'fa fa-chevron-up',
  down: 'fa fa-chevron-down',
  previous: 'fa fa-chevron-left',
  next: 'fa fa-chevron-right',
  today: 'fa fa-screenshot',
  clear: 'fa fa-trash',
  close: 'fa fa-check',
};

export function initDatePickers() {
  for (const el of document.querySelectorAll('.datepicker')) {
    new TempusDominus(el, {
      localization: {
        format: 'dd.MM.yyyy',
      },
      stepping: 5,
      display: {
        icons: TIMEPICKER_ICONS,
        viewMode: 'calendar',
        components: {
          clock: false,
        },
      },
      allowInputToggle: true,
    })
  }
}

export function initTimePickers() {
  for (const el of document.querySelectorAll('.timepicker')) {
    new TempusDominus(el, {
      localization: {
        format: 'HH:mm',
      },
      stepping: 1,
      useCurrent: false,
      display: {
        icons: TIMEPICKER_ICONS,
        viewMode: 'clock',

        components: {
          calendar: false,
          useTwentyfourHour: true,
        },
      },
      defaultDate: new Date('01/01/1980 18:00'),
      allowInputToggle: true,
    })
  }
}

export function initSelectPickers() {
  Array.from(document.querySelectorAll('.multiple-select')).forEach(element => {
    $(element).selectpicker({
      iconBase: 'fa',
      tickIcon: 'fa-check',
    });
  });

  $('.multiple-select.bs-select-hidden').on('loaded.bs.select', function (e) {
    $(e.target).selectpicker('setStyle', 'btn-default');
  });
}
