export type RolesDialogType = 'add' | 'edit' | 'delete'

export const ROLES_DIALOG_ROW_RESET_DELAY_MS = 300

export function syncRolesDialogOpenState(
  dialog: RolesDialogType,
  nextOpen: boolean
) {
  return nextOpen ? dialog : null
}

export function shouldClearRolesCurrentRow(
  dialog: RolesDialogType,
  nextOpen: boolean
) {
  return !nextOpen && dialog !== 'add'
}
