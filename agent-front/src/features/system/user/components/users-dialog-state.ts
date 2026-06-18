export type UsersDialogType = 'add' | 'edit' | 'delete'

export const USERS_DIALOG_ROW_RESET_DELAY_MS = 300

export function syncUsersDialogOpenState(
  dialog: UsersDialogType,
  nextOpen: boolean
) {
  return nextOpen ? dialog : null
}

export function shouldClearUsersCurrentRow(
  dialog: UsersDialogType,
  nextOpen: boolean
) {
  return !nextOpen && dialog !== 'add'
}
