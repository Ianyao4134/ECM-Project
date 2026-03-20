import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import PromptsAdminApp from './PromptsAdminApp.tsx'
import MentorAdminApp from './MentorAdminApp.tsx'
import LoginApp from './LoginApp.tsx'

const path = window.location.pathname
const isPromptsAdmin = path.startsWith('/prompts-admin')
const isMentorAdmin = path.startsWith('/mentor-admin')
const isLogin = path === '/' || path === '/login'
const isStudent = path.startsWith('/student')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isPromptsAdmin ? (
      <PromptsAdminApp />
    ) : isMentorAdmin ? (
      <MentorAdminApp />
    ) : isLogin ? (
      <LoginApp />
    ) : isStudent ? (
      <App />
    ) : (
      <LoginApp />
    )}
  </StrictMode>,
)
