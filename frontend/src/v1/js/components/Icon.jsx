import React from 'react';
import cx from 'classnames';
import PropTypes from 'prop-types';

const Icon = ({ id, className = '' }) => (
  <i className={cx(`fa ${id}`, className)} />
);

Icon.propTypes = {
  id: PropTypes.string.isRequired,
  className: PropTypes.string
};

export default Icon;
