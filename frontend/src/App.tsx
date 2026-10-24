import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import AuthProvider from './auth/AuthProvider'
import { PublicOnly, RequireAuth } from './auth/guards'
import AuthLayout from './components/AuthLayout'
import Layout from './components/Layout'
import ForgotPassword from './pages/ForgotPassword'
import Home from './pages/Home'
import Login from './pages/Login'
import Notebook from './pages/Notebook'
import PruebaCookie from './pages/PruebaCookie'
import PruebaPush from './pages/PruebaPush'
import Register from './pages/Register'
import ResetPassword from './pages/ResetPassword'
import Settings from './pages/Settings'
import Verify from './pages/Verify'
import Welcome from './pages/Welcome'

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Sin sesión: si ya hay sesión, se va al inicio. */}
          <Route element={<PublicOnly />}>
            <Route element={<AuthLayout />}>
              <Route path="bienvenida" element={<Welcome />} />
              <Route path="entrar" element={<Login />} />
              <Route path="registro" element={<Register />} />
              <Route path="verificar" element={<Verify />} />
              <Route path="recuperar" element={<ForgotPassword />} />
              <Route path="restablecer" element={<ResetPassword />} />
            </Route>
          </Route>

          {/* Con sesión: sin ella, se va a la bienvenida. */}
          <Route element={<RequireAuth />}>
            <Route element={<Layout />}>
              <Route index element={<Home />} />
              <Route path="cuaderno" element={<Notebook />} />
              <Route path="ajustes" element={<Settings />} />
            </Route>
          </Route>

          {/* Temporal (Fase 4): pruebas de cookie y push, accesibles con o sin sesión. */}
          <Route element={<Layout />}>
            <Route path="prueba-cookie" element={<PruebaCookie />} />
            <Route path="prueba-push" element={<PruebaPush />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
