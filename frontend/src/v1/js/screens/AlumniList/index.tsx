import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { City, Graduation, UserAlumni } from '~/js/api/types'
import ky from 'ky'
import React, { useState } from 'react'
import Select, { ALL_OPTION } from '~/js/components/Select'
import Card from '~/js/components/Card'

import './alumni.scss'

interface Props {
  programs: Graduation[]
  cities: City[]
}

interface AlumniListRequest {
  program: number
  graduation_year: number
  city: number
}

interface AlumniListResponse {
  alumni: UserAlumni[]
}

function AlumniCard({ user }: { user: UserAlumni }) {
  const telegramLink = user.telegram_username ? `https://t.me/${user.telegram_username}` : ''
  return <Card paddings={16}>
    <img className={'avatar'} src={user.photo}/>
    <div>
      <h3 className={'mt-0'}>{user.first_name} {user.last_name}</h3>
      {user.graduations.map(grad =>
        <p key={grad.program_id}>Graduated from the {grad.program_title} program</p>,
      )}
      {user.city && <p>{user.city.name}, {user.city.country.name}</p>}
      {user.email && <p>{user.email}</p>}
      {user.telegram_username && <p><a href={telegramLink}>{telegramLink}</a></p>}
    </div>
  </Card>
}

function Component({ programs, cities }: Props) {
  const [selectedProgram, setSelectedProgram] = useState<Graduation | null>(null)
  const [selectedCity, setSelectedCity] = useState<City | null>(null)
  const queryParams: Partial<AlumniListRequest> = {}
  if (selectedProgram) {
    queryParams.program = selectedProgram.program_id
    queryParams.graduation_year = selectedProgram.graduation_year
  }
  if (selectedCity) {
    queryParams.city = selectedCity.id
  }

  const { isPending, error, data } = useQuery({
    queryKey: ['alumniList', selectedProgram, selectedCity],
    queryFn: () => ky
      .get('/api/v1/alumni/list/', { searchParams: queryParams })
      .then(res => res.json<AlumniListResponse>()),
  })

  return <>
    <div className={'row mt-n10'}>
      <Select
        className={'col-md-6 mt-10'}
        label={<label>Graduated from</label>}
        isSearchable
        value={selectedProgram?.program_id?.toString()}
        onChange={(val) =>
          val ? setSelectedProgram(programs.find(x => x.program_id == parseInt(val))!) : null
        }
        options={[
          ALL_OPTION,
          ...programs.map(prog => ({
            value: prog.program_id.toString(),
            label: `${prog.program_title} ${prog.graduation_year}`,
          })),
        ]}
      />
      <Select
        className={'col-md-6 mt-10'}
        label={<label>City</label>}
        isSearchable
        value={selectedCity?.id?.toString()}
        onChange={(val) =>
          val ? setSelectedCity(cities.find(x => x.id == parseInt(val))!) : null
        }
        options={[
          ALL_OPTION,
          ...cities.map(city => ({
            value: city.id.toString(),
            label: `${city.name}, ${city.country.name}`,
          })),
        ]}
      />
    </div>
    {isPending && 'Loading...'}
    {error && `An error occurred: ${error.message}`}
    {data && <div className={'alumni-cards mt-10'}>
      {data.alumni.map(user => <AlumniCard key={user.id} user={user}/>)}
    </div>}
  </>
}

export default function App(props: Props) {
  const queryClient = new QueryClient()
  return <QueryClientProvider client={queryClient}>
    <Component {...props}/>
  </QueryClientProvider>
}
