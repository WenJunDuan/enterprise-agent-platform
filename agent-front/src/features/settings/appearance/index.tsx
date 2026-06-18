import { ContentSection } from '../components/content-section'
import { AppearanceForm } from './components/appearance-form'

export function SettingsAppearance() {
  return (
    <ContentSection title='外观' desc='自定义系统外观，并切换浅色或深色主题。'>
      <AppearanceForm />
    </ContentSection>
  )
}
