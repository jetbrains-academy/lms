import Cropper from 'cropperjs';
import $ from 'jquery';
import _throttle from 'lodash-es/throttle';

import { createNotification, getCSRFToken, getTemplate } from 'utils';

const photoAppProps = window.__CSC__.photoApp;

const templates = {
  upload: getTemplate('templateUpload'),
  thumb: getTemplate('templateThumb'),
};

const MESSAGE = {
  unknownError: 'Неизвестная ошибка.',
  imgValidationError: 'Изображение не удовлетворяет требованиям.',
  badRequest: 'Неверный запрос.',
  uploadError: 'Ошибка загрузки файла на сервер. Код: ',
  thumbDoneFail: 'Ошибка создания превью. Код: ',
  thumbSuccess: 'Превью успешно создано',
  imgDimensions: 'Не удалось получить размеры изображения',
  preloadError: 'Ошибка инициализации',
};

let imageData = photoAppProps.photo;

let photoValidation = {
  minWidth: 250,
  minHeight: 350,
  maxFileSize: 5, // Mb
  minThumbWidth: 170,
  minThumbHeight: 238,
};

const xhrOpts = {
  headers: {
    'X-CSRFToken': getCSRFToken(),
  },
};

function getImageMeta(file) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    const url = URL.createObjectURL(file)
    img.onload = () => {
      URL.revokeObjectURL(url)
      resolve({ width: img.width, height: img.height })
    }
    img.onerror = reject
    img.src = url
  })
}

// DOM elements
const uploadContainer = $('#user-photo-upload');
const modalHeader = $('.modal-header', uploadContainer);
const modalBody = $('.modal-body', uploadContainer);

let fn = {
  initPhotoUploaderAndCropper: function () {
    if (photoAppProps.userID === undefined) {
      return;
    }

    $('.login-helper').click(function (e) {
      e.preventDefault();
      $(this).closest('form').submit();
    });

    $('a[href=\'#user-photo-upload\']').click(function () {
      uploadContainer.modal('toggle');
      if (imageData === null) {
        fn.uploadInit();
      }
    });

    uploadContainer.one('shown.bs.modal', function () {
      // Image dimensions is dynamic and we can't get them
      // for cropper inside hidden div (w x h will be
      // 0x0 px before display), init cropper
      // after modal became visible.
      if (imageData !== null) {
        fn.thumbInit(imageData);
      }
    });
  },

  uploadInit: function () {
    let uploadBtn = document.getElementById('simple-btn');
    if (uploadBtn) {
      // Should I remove it manually?
      uploadBtn.removeEventListener('change', fn.uploadValidate)
    }
    modalBody.html(templates.upload());
    uploadBtn = document.getElementById('simple-btn');
    uploadBtn.addEventListener('change', fn.uploadValidate)
  },

  uploadValidate: async (evt) => {
    /** @type File */
    const file = evt.target.files[0]
    if (!file.type.startsWith('image/')) {
      createNotification(MESSAGE.imgValidationError, 'error')
      return
    }
    let info
    try {
      info = await getImageMeta(file)
    } catch (e) {
      createNotification(MESSAGE.imgDimensions, 'error')
      return
    }
    if (
      info.width < photoValidation.minWidth ||
      info.height < photoValidation.minHeight ||
      file.size > photoValidation.maxFileSize * 1024 * 1024
    ) {
      createNotification(MESSAGE.imgValidationError, 'error')
      return
    }
    await fn.uploadProgress(file)
  },

  enableLoadingState: function () {
    modalBody.addClass('load-state');
  },

  disableLoadingState: function () {
    modalBody.removeClass('load-state');
  },

  uploadProgress: async (file) => {
    const formData = new FormData()
    formData.append('photo', file)
    fn.enableLoadingState()
    let response
    try {
      response = await fetch(`/users/${photoAppProps.userID}/profile-update-image/`, {
        ...xhrOpts,
        method: 'POST',
        body: formData,
      })
    } catch (e) {
      fn.uploadError(e)
      return
    }
    if (!response.ok) {
      fn.uploadError(response)
      return
    }

    const respData = await response.json()
    await fn.uploadSuccess(respData, file)
  },

  uploadError: function (resp) {
    fn.disableLoadingState();
    let code;
    switch (resp.status) {
      case 500:
        code = MESSAGE.unknownError;
        break;
      case 403:
        code = MESSAGE.badRequest;
        break;
      default:
        code = resp.message ?? resp.status
    }
    createNotification(MESSAGE.uploadError + code, 'error');
  },

  uploadSuccess: async (respData, file) => {
    if (!respData.success) {
      createNotification(MESSAGE.unknownError, 'error')
      return
    }

    let info
    try {
      info = await getImageMeta(file)
    } catch (e) {
      createNotification(MESSAGE.imgDimensions, 'error')
      return
    }
    respData.width = info.width
    respData.height = info.height
    // Don't forget to update it
    imageData = respData
    fn.thumbInit(respData)
  },

  thumbInit: function (data) {
    fn.enableLoadingState();
    fn.cropperInit(data);
  },

  cropperInit: function (data) {
    // Calculate img dimensions based on a modal body width
    const modalWidth = modalBody.width() - 40; // 40px for padding
    const propWidth = Math.min(data.width, modalWidth);
    const propHeight = Math.round((propWidth / data.width) * data.height);
    modalBody.html(
      templates.thumb({
        url: data.url,
        width: propWidth,
        height: propHeight,
      }),
    );
    let image = modalBody.find('.uploaded-img')[0];
    image.onload = () => {
      let cropper = new Cropper(image, {
        checkCrossOrigin: false,
        viewMode: 1,
        background: true,
        responsive: false,
        autoCropArea: 1,
        // {#                        autoCrop: false,#}
        aspectRatio: 5 / 7,
        dragMode: 'move',
        guides: false,
        movable: false,
        scalable: false,
        rotatable: false,
        zoomable: false,
        zoomOnTouch: false,
        zoomOnWheel: false,
        minContainerWidth: 250,
        minContainerHeight: 250,
        offsetWidth: 0,
        offsetHeight: 0,
        minCropBoxWidth: photoValidation.minThumbWidth,
        minCropBoxHeight: photoValidation.minThumbHeight,
        ready: function () {
          // handlers
          modalBody.find('.-prev').click(function () {
            fn.uploadInit();
          });
          modalBody.find('.save-crop-data').click(function () {
            fn.thumbDone(cropper);
          });
          fn.setCropBox(cropper);
          fn.disableLoadingState();
        },
        //preview: '.thumbnail-img',
      });
    };
    image.src = data.url;
  },

  thumbDone: function (cropper) {
    cropper.disable();
    let cropBox = fn.getCropBox(cropper);

    let data = $.extend({ crop_data: true }, cropBox);
    let opts = $.extend(true, {}, xhrOpts, {
      url: `/users/${photoAppProps.userID}/profile-update-image/`,
      method: 'POST',
      dataType: 'json',
      data: data,
    });
    $.ajax(opts)
      .done(function (data) {
        cropper.enable();
        if (data.success === true) {
          fn.thumbSuccess(cropper, data);
        } else {
          createNotification(data.reason, 'error');
        }
      })
      .fail(function (xhr) {
        cropper.enable();
        createNotification(MESSAGE.thumbDoneFail + xhr.statusText, 'error');
      });
  },

  // Calculate cropbox data relative to img
  getCropBox: function (cropper) {
    return cropper.getData(true);
  },

  // Calculate cropbox data relative to canvas
  setCropBox: function (cropper) {
    if (imageData.cropbox !== undefined) {
      let cropBox = imageData.cropbox;
      cropper.setData(cropBox);
    }
  },

  thumbSuccess: function (cropper, data) {
    cropper.enable();
    $('.thumbnail-img img').attr('src', data.thumbnail);
    createNotification(MESSAGE.thumbSuccess);
    uploadContainer.modal('hide');
  },
};

function restoreTab(targetTab) {
  const tabList = $('.profile-additional-info .nav-tabs');
  if (tabList.find('a[href="' + targetTab + '"]').length > 0) {
    tabList.find('li').removeClass('active').find('a').blur();
    tabList
      .find('a[href="' + targetTab + '"]')
      .tab('show')
      .hover();
  }
}

const throttledFetchConnectedAccounts = _throttle(fetchConnectedAccounts, 1000, {
  leading: true,
  trailing: false,
});

function initConnectedAccountsTab(targetTab) {
  if (!window.__CSC__.socialAccountsApp.isEnabled) {
    return;
  }
  const userID = window.__CSC__.socialAccountsApp.userID;
  if (userID === null) {
    return;
  }
  if (targetTab === '#connected-accounts') {
    fetchConnectedAccounts(userID);
  }
  observeConnectedAccountsTab(userID);
}

function observeConnectedAccountsTab(userID) {
  const tab = document.querySelector('.nav a[href="#connected-accounts"]');
  tab.addEventListener(
    'mouseenter',
    async () => {
      throttledFetchConnectedAccounts(userID);
    },
    { once: true },
  );
}

function fetchConnectedAccounts(userID) {
  if (userID === null) {
    return;
  }
  const container = document.querySelector('.connected-accounts');
  if (container === null || container.getAttribute('data-fetched') === 'true') {
    return;
  }

  const endpoint = `/api/v1/users/${userID}/connected-accounts/`;
  let opts = Object.assign({}, xhrOpts, {
    url: endpoint,
    method: 'GET',
    dataType: 'json',
  });
  $.ajax(opts)
    .done(data => {
      data.edges.forEach(connectedService => {
        const providerContainer = document.querySelector(
          `._connected-account[data-provider="${connectedService.provider}"]`,
        );
        if (providerContainer === null) {
          return;
        }
        const uidElement = providerContainer.querySelector('._uid');
        let idText;
        if (connectedService.login !== null) {
          idText = `Login: ${connectedService.login}`;
        } else {
          idText = `id: ${connectedService.uid}`;
        }
        uidElement.textContent = idText;
        const actionButton = providerContainer.querySelector('button._associate[disabled]');
        if (actionButton !== null) {
          const disconnectLink = actionButton.getAttribute('data-disconnect');
          const form = actionButton.closest('form');
          form.action = disconnectLink;
          form.method = 'POST';
          $(actionButton)
            .text('Отключить')
            .attr('type', 'submit')
            .removeClass('btn-primary')
            .addClass('btn-danger')
            .removeAttr('disabled');
        }
      });
      Array.from(container.querySelectorAll('._associate[disabled]')).forEach(actionButton => {
        actionButton.type = 'submit';
        actionButton.removeAttribute('disabled');
      });
      $(container).attr('data-fetched', true);
    })
    .fail(xhr => {
      createNotification(xhr.statusText, 'error');
      $(container).attr('data-fetched', true);
    });
}

export function launch() {
  const targetTab = window.location.hash;
  initConnectedAccountsTab(targetTab);

  restoreTab(targetTab);
  fn.initPhotoUploaderAndCropper();
}
