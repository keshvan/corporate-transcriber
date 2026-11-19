import { Navigate, Route, Routes } from 'react-router-dom'
import AppLayout from './components/AppLayout'
import MeetingPage from './pages/MeetingPage'
import MeetingsPage from './pages/MeetingsPage'

export default function App() {
  return <Routes>
    <Route element={<AppLayout />}>
      <Route index element={<Navigate to="/meetings" replace />} />
      <Route path="meetings" element={<MeetingsPage />} />
      <Route path="meetings/:meetingId" element={<MeetingPage />} />
      <Route path="*" element={<Navigate to="/meetings" replace />} />
    </Route>
  </Routes>
}
