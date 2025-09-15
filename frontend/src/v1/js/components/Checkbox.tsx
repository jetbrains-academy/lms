import React, { ChangeEvent } from 'react'
import classNames from 'classnames'

interface Props {
  label: string
  required?: boolean
  disabled?: boolean
  checked: boolean
  onChange: (e: ChangeEvent<HTMLInputElement>) => void
  value?: number | string
  className?: string
}


export default function Checkbox(props: Props) {
  const {
    className = '',
    disabled = false,
    required = false,
    label,
    ...rest
  } = props

  const wrapperClass = classNames({
    checkbox: true,
    [className]: className.length > 0,
    disabled,
  })

  return (
    <div className={wrapperClass}>
      <label>
        <input
          type="checkbox"
          required={required}
          {...rest}
        />
        {` ${label}`}
      </label>
    </div>
  )
};
