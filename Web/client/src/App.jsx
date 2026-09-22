import React, { useState } from 'react';
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Navbar from './components/Navbar';
import ProtectedRoute from './components/ProtectedRoute';

// Pages
import Login from './pages/Login';
import Register from './pages/Register';
import ExaminerDashboard from './pages/ExaminerDashboard';
import CreateTest from './pages/CreateTest';
import TestDetailsShare from './pages/TestDetailsShare';
import RegisteredStudents from './pages/RegisteredStudents';
import ExaminerReport from './pages/ExaminerReport';

import StudentDashboard from './pages/StudentDashboard';
import TestRegisterPage from './pages/TestRegisterPage';
import PreTestPanel from './pages/PreTestPanel';
import ExamEnvironment from './pages/ExamEnvironment';
import SubmissionSuccess from './pages/SubmissionSuccess';

function HomeRedirect() {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={user.role === 'examiner' ? '/examiner/dashboard' : '/student/dashboard'} replace />;
}

function AppContent() {
  const [enterModalOpen, setEnterModalOpen] = useState(false);

  return (
    <div className="app-container">
      <Navbar onOpenEnterModal={() => setEnterModalOpen(true)} />
      <main className="main-content">
        <Routes>
          {/* Public Root & Auth */}
          <Route path="/" element={<HomeRedirect />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />

          {/* Examiner Routes */}
          <Route
            path="/examiner/dashboard"
            element={
              <ProtectedRoute allowedRole="examiner">
                <ExaminerDashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/examiner/create-test"
            element={
              <ProtectedRoute allowedRole="examiner">
                <CreateTest />
              </ProtectedRoute>
            }
          />
          <Route
            path="/examiner/test/:testId/share"
            element={
              <ProtectedRoute allowedRole="examiner">
                <TestDetailsShare />
              </ProtectedRoute>
            }
          />
          <Route
            path="/examiner/test/:testId/registrations"
            element={
              <ProtectedRoute allowedRole="examiner">
                <RegisteredStudents />
              </ProtectedRoute>
            }
          />
          <Route
            path="/examiner/test/:testId/report"
            element={
              <ProtectedRoute allowedRole="examiner">
                <ExaminerReport />
              </ProtectedRoute>
            }
          />

          {/* Student / Examinee Routes */}
          <Route
            path="/student/dashboard"
            element={
              <ProtectedRoute allowedRole="examinee">
                <StudentDashboard
                  enterModalOpen={enterModalOpen}
                  setEnterModalOpen={setEnterModalOpen}
                />
              </ProtectedRoute>
            }
          />
          <Route
            path="/test/enter/:testId"
            element={
              <ProtectedRoute allowedRole="examinee">
                <TestRegisterPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/test/register/:testId"
            element={
              <ProtectedRoute allowedRole="examinee">
                <TestRegisterPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/exam/pre-test/:testId"
            element={
              <ProtectedRoute allowedRole="examinee">
                <PreTestPanel />
              </ProtectedRoute>
            }
          />
          <Route
            path="/exam/take/:testId"
            element={
              <ProtectedRoute allowedRole="examinee">
                <ExamEnvironment />
              </ProtectedRoute>
            }
          />
          <Route
            path="/exam/submitted/:testId"
            element={
              <ProtectedRoute allowedRole="examinee">
                <SubmissionSuccess />
              </ProtectedRoute>
            }
          />

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
