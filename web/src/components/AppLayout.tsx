import { NavLink, Outlet } from 'react-router-dom'

export default function AppLayout() {
  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark">P</div><span>Project <b>Memory</b></span></div>
      <nav aria-label="Основная навигация">
        <NavLink to="/meetings" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <span className="nav-icon">◖</span>Встречи
        </NavLink>
      </nav>
    </aside>
    <main className="main">
      <Outlet />
    </main>
  </div>
}
