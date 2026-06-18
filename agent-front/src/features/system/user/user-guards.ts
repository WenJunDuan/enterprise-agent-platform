import { type User } from './data/schema'

const PROTECTED_USERNAMES = new Set(['admin'])

export function isProtectedSystemUser(user: Pick<User, 'username'>) {
  return PROTECTED_USERNAMES.has(user.username.trim().toLowerCase())
}

export function canSelectSystemUser(user: Pick<User, 'username'>) {
  return !isProtectedSystemUser(user)
}
