import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ProgramRun, ProgramRunShort, StudentStatus } from '~/js/api/types'
import ky from 'ky'
import React, { useReducer, useState } from 'react'
import Select from '~/js/components/Select'
import Checkbox from '~/js/components/Checkbox'
import { createNotification, getCSRFToken } from '~/js/utils'

type SelectedProfilesReducerAction = {
  id: number
  selected: boolean
} | {
  id: 'all'
  selected: false
}

function selectedProfilesReducer(state: number[], { id, selected }: SelectedProfilesReducerAction) {
  if (id == 'all') {
    return []
  }
  if (selected && !state.includes(id)) {
    return [...state, id]
  } else if (!selected && state.includes(id)) {
    return state.filter(x => x != id)
  } else {
    return state
  }
}

function PromoteProgramRun({ programRunId }: { programRunId: number }) {
  const qc = useQueryClient()
  const programRunQueryKey = ['programRun', programRunId]
  const { isPending, error, data } = useQuery({
    queryKey: programRunQueryKey,
    queryFn: () => ky.get(`/api/v1/staff/program_runs/${programRunId}/`).then(res => res.json<ProgramRun>()),
  })
  const [selectedProfiles, setProfileSelected] = useReducer(selectedProfilesReducer, [])

  const mutation = useMutation({
    async mutationFn(profileIds: number[]) {
      await ky.post(`/api/v1/alumni/promote/`, {
        headers: { 'X-CSRFToken': getCSRFToken() },
        json: { student_profiles: profileIds },
      })
    },
    onSuccess(_, profileIds) {
      createNotification('Students promoted')
      setProfileSelected({ id: 'all', selected: false })
      qc.invalidateQueries({ queryKey: programRunQueryKey }).then()
    },
    async onError() {
      createNotification('Failed to promote students', 'error')
    },
  })

  if (isPending) {
    return 'Loading...'
  }
  if (error) {
    return `An error occured: ${error.message}`
  }

  const eligibleStudentProfiles = data.student_profiles
    .filter(sp => sp.status == StudentStatus.normal)
  return <>
    <div>
      {eligibleStudentProfiles.map(sp =>
        <Checkbox
          label={`${sp.student.last_name} ${sp.student.first_name}`}
          checked={selectedProfiles.includes(sp.id)}
          onChange={e =>
            setProfileSelected({ id: sp.id, selected: e.target.checked })
          }
        />,
      )}
      {eligibleStudentProfiles.length == 0 &&
        <div className={'my-10'}>
          There are no studying students on the selected program run
        </div>
      }
    </div>
    <button
      className={'btn btn-primary'}
      disabled={mutation.isPending}
      onClick={() => mutation.mutate(selectedProfiles)}
    >
      {mutation.isPending ? 'Loading...' : 'Promote'}
    </button>
  </>
}

function Component() {
  const { isPending, error, data } = useQuery({
    queryKey: ['programRuns'],
    queryFn: () => ky.get('/api/v1/staff/program_runs/').then(res => res.json<ProgramRunShort[]>()),
  })
  const [selectedProgramRun, setSelectedProgramRun] = useState<number | undefined>(undefined)

  if (isPending) {
    return 'Loading...'
  }
  if (error) {
    return `An error occurred: ${error.message}`
  }

  return <>
    <label htmlFor="id_course" className="control-label">
      Select program run
    </label>
    <Select
      value={selectedProgramRun?.toString()}
      isSearchable
      onChange={(val) => setSelectedProgramRun(val ? parseInt(val) : -1)}
      options={[
        ...data.map(run => ({
          value: run.id.toString(),
          label: `${run.title} ${run.start_year}`,
        })),
      ]}
    />
    {selectedProgramRun && <PromoteProgramRun programRunId={selectedProgramRun}/>}
  </>
}

export default function App() {
  const queryClient = new QueryClient()
  return <QueryClientProvider client={queryClient}>
    <Component/>
  </QueryClientProvider>
}
