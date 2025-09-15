import React, { useState } from 'react'
import {
  QueryClient,
  QueryClientProvider,
  skipToken,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import ky from 'ky'
import { createNotification, getCSRFToken } from '~/js/utils'
import { City, Country } from '~/js/api/types'
import Select from '~/js/components/Select'
import { Dropdown } from '@rescui/dropdown'
import { Button } from '@rescui/button'
import { InfoIcon, PlusIcon } from '@rescui/icons'
import { Input } from '@rescui/input'
import { Tooltip } from '@rescui/tooltip'

interface Props {
  inputName: string
  initialCity: City | null
}

function CreateCityButton({ countryId, onCreated }: { countryId: number, onCreated: (city: City) => void }) {
  const [newCityName, setNewCityName] = useState<string>('')
  const [dropdownShown, setDropdownShown] = useState(false)

  const { isPending, mutate } = useMutation({
    mutationFn: () => ky
      .post(`/api/v1/users/cities/`, {
        headers: { 'X-CSRFToken': getCSRFToken() },
        json: { name: newCityName, country_id: countryId },
      })
      .then(resp => resp.json<City>()),
    onSuccess(city) {
      setDropdownShown(false)
      setNewCityName('')
      createNotification('City added')
      onCreated(city)
    },
    async onError() {
      createNotification('Failed to add the city', 'error')
    },
  })
  return <Dropdown
    isOpen={dropdownShown}
    onRequestClose={() => setDropdownShown(false)}
    trigger={
      <Button
        icon={<PlusIcon/>}
        onClick={() => setDropdownShown(true)}
        mode={'outline'}
      />
    }
  >
    <div className={'p-15'}>
      <p>Enter the city name in English, e.g. "Munich", not "München"</p>
      <Input
        placeholder={'City name'}
        value={newCityName}
        onChange={e => setNewCityName(e.target.value)}
        disabled={isPending}
      />
      <Button
        disabled={isPending}
        onClick={() => mutate()}
      >
        Add
      </Button>
    </div>
  </Dropdown>
}

function Component({ inputName, initialCity }: Props) {
  const qc = useQueryClient()
  const [countryId, setCountryId] = useState<number | null>(initialCity?.country?.id ?? null)
  const [cityId, setCityId] = useState<number | null>(initialCity?.id ?? null)

  const countries = useQuery({
    queryKey: ['countries'],
    queryFn: () => ky.get('/api/v1/users/countries/').then(res => res.json<Country[]>()),
  })
  const cities = useQuery({
    queryKey: ['cities', countryId],
    queryFn: countryId != null
      ? () => ky
        .get('/api/v1/users/cities/', { searchParams: { country_id: countryId } })
        .then(res => res.json<City[]>())
      : skipToken,
  })

  function onCityCreated(city: City) {
    qc.invalidateQueries({ queryKey: ['cities', countryId] }).then()
    setCityId(city.id)
  }

  if (countries.isPending) {
    return 'Loading countries...'
  }
  if (countries.isError) {
    return 'Error loading countries'
  }

  return <>
    <div className={'row'} style={{ marginTop: '-10px' }}>
      <div className={'col col-md-6 mt-10'}>
        <label className="control-label">
          Country
        </label>
        <Select
          value={countryId?.toString()}
          isSearchable
          onChange={(val) => setCountryId(val ? parseInt(val) : null)}
          options={countries.data.map(country => ({
            value: country.id.toString(),
            label: country.name,
          }))}
        />
      </div>
      <div className={'col col-md-6 mt-10'}>
        <label className="control-label">
          <span className={'align-middle'}>City</span>
          <Tooltip
            placement="right"
            content="If your city is not listed, you can add it using the + button"
          >
            <InfoIcon theme="light" className={'align-middle ml-5'}/>
          </Tooltip>
        </label>
        {cities.isPending && 'Loading...'}
        {cities.isError && 'Error loading cities'}
        {cities.data && <div className={'flex flex-row'}>
          <Select
            className={'flex-1 mr-10'}
            value={cityId?.toString()}
            isSearchable
            onChange={(val) => setCityId(val ? parseInt(val) : null)}
            options={cities.data.map(city => ({
              value: city.id.toString(),
              label: city.name,
            }))}
          />
          <CreateCityButton countryId={countryId!} onCreated={onCityCreated}/>
        </div>}
      </div>
    </div>
    <input
      className={'hidden'}
      name={inputName}
      value={cityId ? cityId.toString() : ''}
    />
  </>
}

export default function App(props: Props) {
  const queryClient = new QueryClient()
  return <QueryClientProvider client={queryClient}>
    <Component {...props}/>
  </QueryClientProvider>
}
