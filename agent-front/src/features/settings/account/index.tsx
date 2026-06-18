import { ContentSection } from '../components/content-section'
import { AccountForm } from './components/account-form'

export function SettingsAccount() {
  return (
    <ContentSection title='账户' desc='更新账户信息，并设置偏好的语言和时区。'>
      <AccountForm />
    </ContentSection>
  )
}
