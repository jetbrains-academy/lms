import React from 'react';
import cn from 'classnames';
import * as PropTypes from 'prop-types';

const CheckboxButton = ({
  value,
  children,
  onChange = null,
  checked = false,
  className = '',
  ...props
}) => {
  return (
    <button
      {...props}
      className={cn({
        btn: true,
        [className]: true,
        active: checked
      })}
      onClick={() => onChange({ value, checked: !checked })}
      value={value}
    >
      {children}
    </button>
  );
};

CheckboxButton.propTypes = {
  value: PropTypes.string.isRequired,
  checked: PropTypes.bool.isRequired,
  onChange: PropTypes.func.isRequired,
  type: PropTypes.string,
  className: PropTypes.string,
  children: PropTypes.node.isRequired
};

export default CheckboxButton;
