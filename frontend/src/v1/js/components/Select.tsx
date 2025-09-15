import React from 'react'
import { Select as RSelect, SelectProps } from '@rescui/select'

export type SelectValue = string | undefined

export interface SelectOption {
  label: string
  value: SelectValue
}

type Props = {
  options: SelectOption[]
  value: SelectValue
  onChange: (val: SelectValue) => void
} & Omit<SelectProps, 'options' | 'value' | 'onChange'>

export const ALL_OPTION = { value: '-1', label: 'All' }

export default function Select({ value, options, onChange, ...restProps }: Props) {
  const selectedOption = options.find(o => o.value === value)!

  return (
    <RSelect
      {...restProps}
      value={selectedOption}
      onChange={option => onChange(option.value)}
      options={options}
    />
  )
}
