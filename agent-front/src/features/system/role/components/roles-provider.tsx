import React, { useState } from 'react'
import { type Role } from '../model'
import { type RolesDialogType } from './roles-dialog-state'

type RolesContextType = {
  open: RolesDialogType | null
  setOpen: React.Dispatch<React.SetStateAction<RolesDialogType | null>>
  currentRow: Role | null
  setCurrentRow: React.Dispatch<React.SetStateAction<Role | null>>
}

const RolesContext = React.createContext<RolesContextType | null>(null)

export function RolesProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState<RolesDialogType | null>(null)
  const [currentRow, setCurrentRow] = useState<Role | null>(null)

  return (
    <RolesContext value={{ open, setOpen, currentRow, setCurrentRow }}>
      {children}
    </RolesContext>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export const useRoles = () => {
  const context = React.useContext(RolesContext)

  if (!context) {
    throw new Error('useRoles has to be used within <RolesContext>')
  }

  return context
}
