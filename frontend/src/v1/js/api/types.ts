export enum StudentType {
  regular = 'regular',
  invited = 'invited',
  alumni = 'alumni',
}

export enum StudentStatus {
  normal = 'normal',
  expelled = 'expelled',
  graduated = 'graduated',
}

export enum Gender {
  male = 'M',
  female = 'F',
  other = 'o',
}

export interface Graduation {
  program_id: number
  program_title: string
  graduation_year: number
}

export interface UserShort {
  id: number
  first_name: string
  last_name: string
  gender: Gender
}

export interface UserAlumni extends UserShort {
  username: string
  city: City
  email: string
  photo: string
  telegram_username: string
  graduations: Graduation[]
}

export interface StudentProfile {
  id: number
  type: StudentType
  status: StudentStatus
  year_of_admission: number
  year_of_curriculum: number
  student: UserShort
}

export interface ProgramRunShort {
  id: number
  title: string
  code: string
  start_year: number
}

export interface ProgramRun extends ProgramRunShort {
  student_profiles: StudentProfile[]
}

export interface Country {
  id: number
  code: string
  name: string
}

export interface City {
  id: number
  name: string
  country: Country
}
