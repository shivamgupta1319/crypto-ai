import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Scanner from './pages/Scanner'
import Portfolio from './pages/Portfolio'
import Backtest from './pages/Backtest'
import News from './pages/News'
import Settings from './pages/Settings'
import Agent from './pages/Agent'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="scanner" element={<Scanner />} />
          <Route path="portfolio" element={<Portfolio />} />
          <Route path="backtest" element={<Backtest />} />
          <Route path="news" element={<News />} />
          <Route path="agent" element={<Agent />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
