import { cardCn, CardProps } from '@rescui/card'
import clsx from 'clsx';
import React from 'react';
import { PropsWithChildren } from 'react'

interface Props extends CardProps {
  className?: string
  href?: string
}

export default function Card(
  {
    className,
    children,
    href,
    ...cardProps
  }: PropsWithChildren<Props>,
) {
  const Tag = href ? 'a' : 'div';
  return <Tag
    className={clsx(cardCn(cardProps), className, 'resc-card')}
    href={href}
  >
    {children}
  </Tag>
}
