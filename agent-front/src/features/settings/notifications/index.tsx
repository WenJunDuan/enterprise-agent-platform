import { ContentSection } from '../components/content-section'
import { NotificationsForm } from './components/notifications-form'

export function SettingsNotifications() {
  return (
    <ContentSection title='通知' desc='配置您接收系统通知的方式。'>
      <NotificationsForm />
    </ContentSection>
  )
}
