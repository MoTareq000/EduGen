import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Navbar } from './components/layout/Navbar';
import { AuthPage } from './pages/AuthPage';
import { OAuthCallback } from './pages/OAuthCallback';
import { ExamGenerator } from './pages/ExamGenerator';
import { GradingHub } from './pages/GradingHub';
import { Students } from './pages/Students';
import { EduGenInsights } from './pages/EduGenInsights';
import { MyExams } from './pages/MyExams';
import { ExamWindow } from './pages/ExamWindow';
import { Results } from './pages/Results';
import { Background } from './components/layout/Background';

import './index.css';

// Protected Route Wrapper
const ProtectedRoute = ({ children, allowedRoles }: { children: React.ReactNode, allowedRoles?: string[] }) => {
  const { user } = useAuth();

  if (!user) {
    return <Navigate to="/auth" replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to={user.role === 'instructor' ? '/exams' : '/'} replace />;
  }

  return <>{children}</>;
};

function AppRoutes() {
  return (
    <>
      <Background />
      <Navbar />
      <main className="container mx-auto px-4 pt-28 pb-24 md:pb-10">
        <Routes>
          <Route path="/auth" element={<AuthPage />} />
          <Route path="/oauth/callback" element={<OAuthCallback />} />

          {/* Instructor Routes */}
          <Route path="/exams" element={
            <ProtectedRoute allowedRoles={['instructor']}>
              <ExamGenerator />
            </ProtectedRoute>
          } />
          <Route path="/grading" element={
            <ProtectedRoute allowedRoles={['instructor']}>
              <GradingHub />
            </ProtectedRoute>
          } />
          <Route path="/students" element={
            <ProtectedRoute allowedRoles={['instructor']}>
              <Students />
            </ProtectedRoute>
          } />
          <Route path="/insights" element={
            <ProtectedRoute allowedRoles={['instructor']}>
              <EduGenInsights />
            </ProtectedRoute>
          } />

          {/* Student Routes */}
          <Route path="/" element={
            <ProtectedRoute allowedRoles={['student']}>
              <MyExams />
            </ProtectedRoute>
          } />
          <Route path="/results" element={
            <ProtectedRoute allowedRoles={['student']}>
              <Results />
            </ProtectedRoute>
          } />
          <Route path="/take-exam/:id" element={
            <ProtectedRoute allowedRoles={['student']}>
              <ExamWindow />
            </ProtectedRoute>
          } />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  );
}

function App() {
  return (
    <AuthProvider>
      <Router>
        <AppRoutes />
      </Router>
    </AuthProvider>
  );
}

export default App;
