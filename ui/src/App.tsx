import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Component, type ReactNode } from 'react'
import Layout from './components/Layout'
import TaskList from './pages/TaskList'
import SubmitExpense from './pages/SubmitExpense'
import TaskDetail from './pages/TaskDetail'

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null }
  static getDerivedStateFromError(error: Error) { return { error } }
  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-50">
          <div className="text-center p-8">
            <p className="text-red-600 font-medium mb-2">页面出现错误</p>
            <p className="text-sm text-gray-500 mb-4">{(this.state.error as Error).message}</p>
            <button
              onClick={() => this.setState({ error: null })}
              className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm hover:bg-blue-700"
            >
              重试
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

function NotFound() {
  return (
    <div className="text-center py-20 text-gray-500">
      <p className="text-3xl font-semibold mb-2">404</p>
      <p className="text-sm mb-4">页面不存在</p>
      <a href="/" className="text-blue-600 text-sm hover:underline">返回首页</a>
    </div>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<TaskList />} />
            <Route path="submit" element={<SubmitExpense />} />
            <Route path="tasks/:id" element={<TaskDetail />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  )
}
