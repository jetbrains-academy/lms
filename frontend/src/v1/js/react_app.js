import React from 'react';
import ReactDOM from 'react-dom';

import { showComponentError } from 'utils';

export function renderComponent(el) {
  let componentName = el.dataset['component'];
  import(/* webpackChunkName: "[request]" */ `screens/${componentName}/index`)
    .then(component => {
      // Not the best place for loading polyfills since we could do it
      // in parallel with application source, but this limitation allows
      // to store all dependencies in one place.
      // TODO: Optimization: add support for data-polyfills
      if (Object.prototype.hasOwnProperty.call(component, 'polyfills')) {
        return Promise.all(component.polyfills).then(() => component);
      } else {
        return component;
      }
    })
    .then(component => {
      let props = {
        initialState: {}
      };
      let init = el.dataset['init'];
      if (init !== null) {
        let data = JSON.parse(init);
        if (data.props !== undefined) {
          Object.keys(data.props).map(k => {
            props[k] = data.props[k];
          });
          delete data.props;
        }
        props.initialState = data.state || {};
      }
      let Component = component.default;
      ReactDOM.render(React.createElement(Component, props), el);
    })
    .catch(error => showComponentError(error));
}
