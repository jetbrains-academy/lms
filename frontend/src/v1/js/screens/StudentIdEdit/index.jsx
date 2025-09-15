import { useState } from 'react'
import { QueryClient, QueryClientProvider, useMutation } from '@tanstack/react-query'
import { createNotification } from 'utils'
import ky from 'ky'
import { getCSRFToken } from '../../utils'

function Component({ initialStudentId, profileId }) {
  const [studentId, setStudentId] = useState(initialStudentId)
  const [isEditing, setEditing] = useState(false)
  const [editingStudentId, setEditingStudentId] = useState(initialStudentId)

  const mutation = useMutation({
    async mutationFn() {
      await ky.post(`/api/v1/profiles/${profileId}/set-student-id`, {
        headers: { 'X-CSRFToken': getCSRFToken() },
        json: { student_id: editingStudentId },
      })
    },
    onSuccess() {
      createNotification('Student id updated')
      setStudentId(editingStudentId)
      setEditing(false)
    },
    async onError(err) {
      let errors = []
      try {
        const errData = await err.response.json()
        errors = errData.errors.map(e => e.message)
      } catch (e) {
        console.error(e)
      }
      if (errors.length == 0) {
        createNotification('Failed to update student id', 'error')
      } else {
        for (const error of errors) {
          createNotification(error, 'error')
        }
      }
    },
  })

  function startEditing() {
    setEditingStudentId(studentId)
    setEditing(true)
  }

  if (isEditing) {
    return <div style={{
      display: 'flex',
      gap: '5px',
      alignItems: 'center',
    }}>
      <input
        className={'form-control'}
        style={{
          width: 'unset',
          flex: '1',
        }}
        value={editingStudentId}
        onChange={e => setEditingStudentId(e.target.value)}
      />
      {mutation.isPending
        ? <i className="fa fa-refresh fa-spin"/>
        : <>
          <button onClick={mutation.mutate} className={'btn btn-default btn-sm'}>
            <i className="fa fa-floppy-o"/>
          </button>
          <button onClick={() => setEditing(false)} className={'btn btn-default btn-sm'}>
            <i className="fa fa-times"/>
          </button>
        </>
      }
    </div>
  } else {
    return <div style={{
      display: 'flex',
      gap: '10px',
      alignItems: 'center',
    }}>
      <span>{studentId}</span>
      <button onClick={startEditing} className={'btn btn-default btn-sm'}>
        <i className="fa fa-pencil"/>
      </button>
    </div>
  }
}

export default function App(props) {
  const queryClient = new QueryClient()
  return <QueryClientProvider client={queryClient}>
    <Component initialStudentId={props.studentId} profileId={props.profileId}/>
  </QueryClientProvider>
}
