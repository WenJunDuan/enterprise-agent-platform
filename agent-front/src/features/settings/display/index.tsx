import { ContentSection } from '../components/content-section'
import { DisplayForm } from './components/display-form'

export function SettingsDisplay() {
  return (
    <ContentSection title='显示' desc='控制系统中需要展示的内容项。'>
      <DisplayForm />
    </ContentSection>
  )
}
