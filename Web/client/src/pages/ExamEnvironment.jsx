import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import {
  Clock,
  AlertTriangle,
  Send,
  Play,
  CheckCircle2,
  XCircle,
  Code2,
  ChevronLeft,
  ChevronRight,
  Maximize2,
  Minimize2,
  ShieldAlert,
  RotateCcw,
  Copy,
  Check,
  Bookmark,
  Terminal,
  Columns,
  Eye,
  EyeOff,
  CheckCheck,
  PanelRightClose,
  PanelRightOpen,
  Sparkles,
  Camera,
  ShieldCheck,
  Mic,
  UserCheck,
  UserX,
} from 'lucide-react';

const DEFAULT_CODE_TEMPLATES = {
  javascript: `const fs = require('fs');

function solve() {
    // Read all input from standard input (stdin)
    const input = fs.readFileSync(0, 'utf-8').trim();
    if (!input) return;

    // Write your solution below
    console.log(input);
}

solve();`,

  python: `import sys

def solve():
    # Read all input from standard input (sys.stdin)
    input_data = sys.stdin.read().strip()
    if not input_data:
        return

    # Write your solution below
    print(input_data)

if __name__ == '__main__':
    solve()`,

  cpp: `#include <iostream>
#include <vector>
#include <string>
#include <algorithm>

using namespace std;

int main() {
    // Fast I/O
    ios_base::sync_with_stdio(false);
    cin.tie(NULL);

    // Read input and write your solution below
    string line;
    while (getline(cin, line)) {
        cout << line << "\\n";
    }

    return 0;
}`,

  java: `import java.util.*;
import java.io.*;

public class Main {
    public static void main(String[] args) throws Exception {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
        String line = br.readLine();
        if (line == null) return;

        // Write your solution below
        System.out.println(line);
    }
}`,
};

export default function ExamEnvironment() {
  const { testId } = useParams();
  const navigate = useNavigate();

  const [examData, setExamData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [currentIndex, setCurrentIndex] = useState(0);

  // Answers state:
  // { [qId]: { selectedOption: number|null, code: string, language: string, codeByLang: {}, isSavedByUser: boolean } }
  const [answers, setAnswers] = useState({});

  // Question metadata tracking
  const [visitedQuestions, setVisitedQuestions] = useState(new Set());
  const [markedForReview, setMarkedForReview] = useState(new Set());
  const [paletteFilter, setPaletteFilter] = useState('all'); // 'all', 'answered', 'unanswered', 'marked'

  // Coding execution output state:
  // codeExecution[qId] = { runResult: {...}, submitResult: {...} }
  const [codeExecution, setCodeExecution] = useState({});
  const [runningCode, setRunningCode] = useState(false);
  const [submittingCode, setSubmittingCode] = useState(false);
  const [activeConsoleTab, setActiveConsoleTab] = useState('testcase'); // 'testcase' | 'run_result' | 'submit_result'
  const [selectedTestCaseIndex, setSelectedTestCaseIndex] = useState(0);
  const [customStdin, setCustomStdin] = useState('');
  const [consoleHeightMode, setConsoleHeightMode] = useState('normal'); // 'normal' | 'expanded' | 'collapsed'
  const [copiedCode, setCopiedCode] = useState(false);

  // Adjustable Screen & Layout states
  const [splitLayout, setSplitLayout] = useState('standard'); // 'standard' (420/1fr), 'wide' (300/1fr), 'equal' (1fr/1fr), 'focus' (code only)
  const [isFullscreenEditor, setIsFullscreenEditor] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Non-intrusive In-App Toast notification (replaces OS alert)
  const [toast, setToast] = useState(null);

  // Proctoring & Violations state
  const [violationsCount, setViolationsCount] = useState(0);
  const [showWarningModal, setShowWarningModal] = useState(false);
  const [autoSubmitting, setAutoSubmitting] = useState(false);
  const [autoSubmitReason, setAutoSubmitReason] = useState('');

  // AI Proctoring Engine state
  const [aiProctorActive, setAiProctorActive] = useState(false);
  const [showAiHud, setShowAiHud] = useState(true);
  const [aiHudMinimized, setAiHudMinimized] = useState(false);
  const [aiTelemetry, setAiTelemetry] = useState(null);
  const [activeAiAlert, setActiveAiAlert] = useState(null);
  const lastAiEventCountRef = useRef(0);

  // Submit confirmation modal
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Remaining time in seconds to endTime
  const [secondsRemaining, setSecondsRemaining] = useState(null);

  const hasLoadedRef = useRef(false);
  const violationLockedRef = useRef(false);
  const textareaRef = useRef(null);

  useEffect(() => {
    initExam();
  }, [testId]);

  // Mark question as visited when index changes
  useEffect(() => {
    if (examData && examData.questions && examData.questions[currentIndex]) {
      const q = examData.questions[currentIndex];
      setVisitedQuestions((prev) => new Set([...prev, q.id]));
      setSelectedTestCaseIndex(0);
      setCustomStdin('');
    }
  }, [currentIndex, examData]);

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => {
      setToast((prev) => (prev?.message === message ? null : prev));
    }, 3500);
  };

  const initExam = async () => {
    try {
      setLoading(true);
      const data = await api.getTestForExam(testId);
      setExamData(data);

      // Initialize / resume session on backend
      const session = await api.startExam(testId);

      const restoredAnswers = {};
      const restoredVisited = new Set();

      if (session.answers && session.answers.length > 0) {
        session.answers.forEach((ans) => {
          restoredVisited.add(ans.questionId);
          const lang = ans.language || 'javascript';
          const defaultTemplates = { ...DEFAULT_CODE_TEMPLATES };
          if (ans.code) {
            defaultTemplates[lang] = ans.code;
          }

          restoredAnswers[ans.questionId] = {
            selectedOption: ans.selectedOption !== undefined ? ans.selectedOption : null,
            code: ans.code || defaultTemplates[lang],
            language: lang,
            codeByLang: defaultTemplates,
            isSavedByUser: Boolean(ans.code || ans.selectedOption !== undefined),
          };
        });
      }

      // Initialize defaults for remaining questions
      data.questions.forEach((q) => {
        if (!restoredAnswers[q.id]) {
          const lang = q.language || 'javascript';
          const templates = { ...DEFAULT_CODE_TEMPLATES };
          if (q.starterCode && q.starterCode.trim()) {
            templates[lang] = q.starterCode;
          }

          restoredAnswers[q.id] = {
            selectedOption: null,
            code: templates[lang],
            language: lang,
            codeByLang: templates,
            isSavedByUser: false,
          };
        }
      });

      if (data.questions.length > 0) {
        restoredVisited.add(data.questions[0].id);
      }

      setAnswers(restoredAnswers);
      setVisitedQuestions(restoredVisited);

      const totalBrowserViolations =
        (session.proctoring?.tabSwitchCount || 0) + (session.proctoring?.fullscreenExitCount || 0);
      setViolationsCount(totalBrowserViolations);

      // Connect and initialize Multimodal AI Proctoring Service
      if (data.registration?.photoUrl) {
        try {
          await api.aiStartSession({
            testId: data.test.testId,
            studentId: data.registration._id || session.userId,
            studentName: data.registration.formData?.name || 'Candidate',
            photoUrl: data.registration.photoUrl,
          });
          setAiProctorActive(true);
        } catch (aiErr) {
          console.warn('AI Proctoring service initialization notice:', aiErr.message);
        }
      }

      // Prompt fullscreen
      if (!document.fullscreenElement) {
        try {
          await document.documentElement.requestFullscreen();
        } catch (_) {}
      }

      hasLoadedRef.current = true;
    } catch (err) {
      if (err.data && err.data.alreadySubmitted) {
        navigate(`/exam/submitted/${testId}`, { replace: true });
        return;
      }
      showToast(err.message || 'Failed to initialize exam', 'error');
      navigate('/student/dashboard');
    } finally {
      setLoading(false);
    }
  };

  // Timer countdown to test endTime
  useEffect(() => {
    if (!examData) return;

    const interval = setInterval(() => {
      const now = new Date().getTime();
      const end = new Date(examData.test.endTime).getTime();
      const diffSec = Math.floor((end - now) / 1000);

      if (diffSec <= 0) {
        setSecondsRemaining(0);
        clearInterval(interval);
        triggerAutoSubmit('time_up');
      } else {
        setSecondsRemaining(diffSec);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [examData]);

  // AI Proctoring Telemetry Polling & Real-time Alerts Listener
  useEffect(() => {
    if (!hasLoadedRef.current || autoSubmitting) return;

    const pollAiStatus = async () => {
      try {
        const res = await api.aiGetStatus();
        if (res.active) {
          setAiProctorActive(true);
          setAiTelemetry(res.telemetry);

          if (res.events && res.events.length > lastAiEventCountRef.current) {
            const newEvents = res.events.slice(lastAiEventCountRef.current);
            lastAiEventCountRef.current = res.events.length;
            const latestEv = newEvents[newEvents.length - 1];

            setActiveAiAlert(latestEv);
            setViolationsCount((prev) => prev + newEvents.length);

            showToast(`⚠️ AI Warning: ${latestEv.message}`, 'error');

            setTimeout(() => {
              setActiveAiAlert((cur) => (cur?.id === latestEv.id ? null : cur));
            }, 6000);
          }
        }
      } catch (_) {}
    };

    const interval = setInterval(pollAiStatus, 2000);
    return () => clearInterval(interval);
  }, [loading, autoSubmitting]);

  // Clean shutdown of AI Proctoring session on unmount
  useEffect(() => {
    return () => {
      api.aiStopSession().catch(() => {});
    };
  }, []);

  // Anti-cheating listeners: tab switch and fullscreen exit
  useEffect(() => {
    if (!hasLoadedRef.current) return;

    const handleVisibilityChange = () => {
      if (document.hidden) {
        handleViolationEvent('TAB_SWITCH', 'Switched browser tab or minimized window');
      }
    };

    const handleWindowBlur = () => {
      handleViolationEvent('TAB_SWITCH', 'Window focus lost');
    };

    const handleFullscreenChange = () => {
      if (!document.fullscreenElement) {
        handleViolationEvent('FULLSCREEN_EXIT', 'Exited full-screen mode');
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('blur', handleWindowBlur);
    document.addEventListener('fullscreenchange', handleFullscreenChange);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('blur', handleWindowBlur);
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
    };
  }, [loading]);

  const handleViolationEvent = async (type, message) => {
    if (violationLockedRef.current || autoSubmitting) return;
    violationLockedRef.current = true;

    try {
      const res = await api.logViolation({ testId, type, message });
      setViolationsCount(res.totalViolations);

      if (res.mustAutoSubmit) {
        triggerAutoSubmit('violation_limit');
      } else if (res.isWarning) {
        setShowWarningModal(true);
      }
    } catch (e) {
      console.error('Failed to log violation:', e);
    } finally {
      setTimeout(() => {
        violationLockedRef.current = false;
      }, 1500);
    }
  };

  const reEnterFullscreen = async () => {
    try {
      if (!document.fullscreenElement) {
        await document.documentElement.requestFullscreen();
      }
      setShowWarningModal(false);
    } catch (e) {
      setShowWarningModal(false);
    }
  };

  // MCQ Selection
  const handleSelectMcq = async (qId, optIndex) => {
    const updated = {
      ...answers,
      [qId]: {
        ...answers[qId],
        selectedOption: optIndex,
        isSavedByUser: true,
      },
    };
    setAnswers(updated);
    setVisitedQuestions((prev) => new Set([...prev, qId]));

    try {
      await api.saveAnswer({
        testId,
        questionId: qId,
        questionType: 'mcq',
        selectedOption: optIndex,
      });
      showToast('MCQ option selected and saved');
    } catch (e) {
      console.error('Autosave error:', e);
    }
  };

  // Clear MCQ selection
  const handleClearMcq = async (qId) => {
    const updated = {
      ...answers,
      [qId]: {
        ...answers[qId],
        selectedOption: null,
        isSavedByUser: false,
      },
    };
    setAnswers(updated);

    try {
      await api.saveAnswer({
        testId,
        questionId: qId,
        questionType: 'mcq',
        selectedOption: null,
      });
      showToast('Selection cleared');
    } catch (e) {
      console.error('Clear answer error:', e);
    }
  };

  // Toggle Mark for Review
  const toggleMarkForReview = (qId) => {
    setMarkedForReview((prev) => {
      const next = new Set(prev);
      const isAdding = !next.has(qId);
      if (isAdding) {
        next.add(qId);
        showToast('Question marked for review');
      } else {
        next.delete(qId);
        showToast('Removed mark for review');
      }
      return next;
    });
  };

  // Code editor change
  const handleCodeChange = (qId, newCode) => {
    const currentLang = answers[qId]?.language || 'javascript';
    const codeByLang = {
      ...(answers[qId]?.codeByLang || {}),
      [currentLang]: newCode,
    };

    setAnswers({
      ...answers,
      [qId]: {
        ...answers[qId],
        code: newCode,
        codeByLang,
        isSavedByUser: true,
      },
    });
  };

  // Language Change: Switch cleanly without code corruption
  const handleLanguageChange = (qId, newLang) => {
    const currentAns = answers[qId] || {};
    const oldLang = currentAns.language || 'javascript';
    const oldCode = currentAns.code;

    // Save current code to previous language dictionary
    const updatedCodeByLang = {
      ...(currentAns.codeByLang || DEFAULT_CODE_TEMPLATES),
      [oldLang]: oldCode,
    };

    // Load template or previous work for new language
    const newCode = updatedCodeByLang[newLang] || DEFAULT_CODE_TEMPLATES[newLang] || '// Write solution here\n';
    updatedCodeByLang[newLang] = newCode;

    setAnswers({
      ...answers,
      [qId]: {
        ...currentAns,
        language: newLang,
        code: newCode,
        codeByLang: updatedCodeByLang,
      },
    });
    showToast(`Switched editor to ${newLang.toUpperCase()}`);
  };

  // Reset Code to default template
  const handleResetTemplate = (qId) => {
    const currentLang = answers[qId]?.language || 'javascript';
    const defaultTemplate = DEFAULT_CODE_TEMPLATES[currentLang] || '';

    const updatedCodeByLang = {
      ...(answers[qId]?.codeByLang || {}),
      [currentLang]: defaultTemplate,
    };

    setAnswers({
      ...answers,
      [qId]: {
        ...answers[qId],
        code: defaultTemplate,
        codeByLang: updatedCodeByLang,
      },
    });
    showToast(`Reset code to default ${currentLang} template`);
  };

  // Copy Code button
  const handleCopyCode = (code) => {
    if (!code) return;
    navigator.clipboard.writeText(code);
    setCopiedCode(true);
    showToast('Code copied to clipboard');
    setTimeout(() => setCopiedCode(false), 2000);
  };

  // Tab & Enter key support inside editor
  const handleEditorKeyDown = (e, qId) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const textarea = e.target;
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const val = textarea.value;

      // Insert 4 spaces
      const updated = val.substring(0, start) + '    ' + val.substring(end);
      handleCodeChange(qId, updated);

      setTimeout(() => {
        textarea.selectionStart = textarea.selectionEnd = start + 4;
      }, 0);
    } else if (e.key === 'Enter') {
      const textarea = e.target;
      const start = textarea.selectionStart;
      const val = textarea.value;

      // Match current line's leading whitespace to auto-indent
      const lineStart = val.lastIndexOf('\n', start - 1) + 1;
      const currentLine = val.substring(lineStart, start);
      const match = currentLine.match(/^(\s+)/);

      if (match) {
        e.preventDefault();
        const indent = match[1];
        const updated = val.substring(0, start) + '\n' + indent + val.substring(start);
        handleCodeChange(qId, updated);

        setTimeout(() => {
          textarea.selectionStart = textarea.selectionEnd = start + 1 + indent.length;
        }, 0);
      }
    }
  };

  // 1. RUN CODE: Test against Sample Public Test Cases or Custom Stdin
  const handleRunCode = async (q) => {
    const code = answers[q.id]?.code;
    const lang = answers[q.id]?.language || q.language || 'javascript';
    if (!code || !code.trim()) {
      showToast('Please write code before executing', 'error');
      return;
    }

    setRunningCode(true);
    setActiveConsoleTab('run_result');
    if (consoleHeightMode === 'collapsed') setConsoleHeightMode('normal');

    try {
      const sampleCases = q.sampleTestCases || [];
      let stdinToUse = '';
      let expectedOut = '';

      if (selectedTestCaseIndex === -1) {
        // Custom input
        stdinToUse = customStdin;
        expectedOut = '';
      } else if (sampleCases[selectedTestCaseIndex]) {
        stdinToUse = sampleCases[selectedTestCaseIndex].input || '';
        expectedOut = sampleCases[selectedTestCaseIndex].expectedOutput || '';
      }

      const res = await api.runCode({
        sourceCode: code,
        language: lang,
        input: stdinToUse,
        expectedOutput: expectedOut,
      });

      setCodeExecution((prev) => ({
        ...prev,
        [q.id]: {
          ...(prev[q.id] || {}),
          runResult: {
            ...res,
            input: stdinToUse,
            expectedOutput: expectedOut,
          },
        },
      }));

      // Also autosave answer & mark answered
      await api.saveAnswer({
        testId,
        questionId: q.id,
        questionType: 'coding',
        code,
        language: lang,
      });

      setAnswers((prev) => ({
        ...prev,
        [q.id]: {
          ...prev[q.id],
          isSavedByUser: true,
        },
      }));

      showToast(res.passed ? 'Testcase Passed! (Sample Run)' : 'Sample Run Finished', res.passed ? 'success' : 'error');
    } catch (err) {
      setCodeExecution((prev) => ({
        ...prev,
        [q.id]: {
          ...(prev[q.id] || {}),
          runResult: {
            success: false,
            stderr: err.message || 'Execution failed',
            status: 'Error',
            passed: false,
          },
        },
      }));
      showToast('Execution error: ' + (err.message || 'Run failed'), 'error');
    } finally {
      setRunningCode(false);
    }
  };

  // 2. SUBMIT CODE: Evaluates against ALL Test Cases (including HIDDEN) just like LeetCode
  const handleSubmitCode = async (q) => {
    const code = answers[q.id]?.code;
    const lang = answers[q.id]?.language || q.language || 'javascript';
    if (!code || !code.trim()) {
      showToast('Please write code before submitting', 'error');
      return;
    }

    setSubmittingCode(true);
    setActiveConsoleTab('submit_result');
    if (consoleHeightMode === 'collapsed') setConsoleHeightMode('expanded');

    try {
      const res = await api.submitCodeQuestion({
        testId,
        questionId: q.id,
        sourceCode: code,
        language: lang,
      });

      setCodeExecution((prev) => ({
        ...prev,
        [q.id]: {
          ...(prev[q.id] || {}),
          submitResult: res,
        },
      }));

      // Mark question as answered in state
      setAnswers((prev) => ({
        ...prev,
        [q.id]: {
          ...prev[q.id],
          isSavedByUser: true,
        },
      }));

      if (res.status === 'Accepted') {
        showToast(`🎉 Accepted! All ${res.totalCases}/${res.totalCases} test cases passed! Question marked as Answered.`, 'success');
      } else {
        showToast(`${res.status}: ${res.passedCases}/${res.totalCases} test cases passed. Solution saved.`, 'error');
      }
    } catch (err) {
      showToast(err.message || 'Failed to evaluate code submission', 'error');
    } finally {
      setSubmittingCode(false);
    }
  };

  // Trigger submission (manual or auto)
  const triggerAutoSubmit = async (reason) => {
    setAutoSubmitting(true);
    setAutoSubmitReason(reason);

    try {
      const formattedAnswers = Object.entries(answers).map(([questionId, ans]) => ({
        questionId,
        selectedOption: ans.selectedOption,
        code: ans.code,
        language: ans.language,
      }));

      await api.submitExam({
        testId,
        answers: formattedAnswers,
        reason,
      });

      await api.aiStopSession().catch(() => {});

      if (document.fullscreenElement) {
        try { document.exitFullscreen(); } catch (_) {}
      }

      navigate(`/exam/submitted/${testId}`, { replace: true });
    } catch (err) {
      console.error('Auto submit error:', err);
      await api.aiStopSession().catch(() => {});
      navigate(`/exam/submitted/${testId}`, { replace: true });
    }
  };

  const handleManualSubmit = async () => {
    setSubmitting(true);
    try {
      const formattedAnswers = Object.entries(answers).map(([questionId, ans]) => ({
        questionId,
        selectedOption: ans.selectedOption,
        code: ans.code,
        language: ans.language,
      }));

      await api.submitExam({
        testId,
        answers: formattedAnswers,
        reason: 'manual',
      });

      await api.aiStopSession().catch(() => {});

      if (document.fullscreenElement) {
        try { document.exitFullscreen(); } catch (_) {}
      }

      navigate(`/exam/submitted/${testId}`, { replace: true });
    } catch (err) {
      showToast(err.message || 'Failed to submit exam', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const formatTimer = (totalSec) => {
    if (totalSec === null) return '--:--:--';
    if (totalSec <= 0) return '00:00:00';
    const h = Math.floor(totalSec / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = totalSec % 60;
    const pad = (n) => String(n).padStart(2, '0');
    return `${pad(h)}:${pad(m)}:${pad(s)}`;
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#0f172a', color: '#ffffff' }}>
        Loading secure examination environment...
      </div>
    );
  }

  if (autoSubmitting) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#0f172a', color: '#ffffff', padding: 24, textAlign: 'center' }}>
        <AlertTriangle size={48} color="var(--danger)" style={{ marginBottom: 16 }} />
        <h2 style={{ fontSize: 22, fontWeight: 700, marginBottom: 8 }}>
          {autoSubmitReason === 'time_up'
            ? 'Test Time Expired — Submitting Exam...'
            : 'Anti-Cheating Violation Limit Exceeded — Submitting Exam...'}
        </h2>
        <p style={{ color: '#94a3b8', fontSize: 14 }}>
          Your answers are being securely saved and evaluated.
        </p>
      </div>
    );
  }

  const questions = examData?.questions || [];
  const currentQ = questions[currentIndex];

  // Robust answer checking logic
  const isQuestionAnswered = (q) => {
    const ans = answers[q.id];
    if (!ans) return false;

    if (q.questionType === 'mcq') {
      return ans.selectedOption !== undefined && ans.selectedOption !== null;
    } else {
      if (ans.isSavedByUser) return true;
      const currentCode = (ans.code || '').trim();
      const defaultCode = (DEFAULT_CODE_TEMPLATES[ans.language || 'javascript'] || '').trim();
      return currentCode.length > 0 && currentCode !== defaultCode;
    }
  };

  const isQuestionMarked = (q) => markedForReview.has(q.id);
  const isQuestionVisited = (q) => visitedQuestions.has(q.id);

  const answeredCount = questions.filter(isQuestionAnswered).length;
  const markedCount = questions.filter(isQuestionMarked).length;
  const unansweredCount = questions.length - answeredCount;

  // Question palette filter
  const filteredQuestions = questions.map((q, idx) => ({ q, idx })).filter(({ q }) => {
    if (paletteFilter === 'answered') return isQuestionAnswered(q);
    if (paletteFilter === 'unanswered') return !isQuestionAnswered(q);
    if (paletteFilter === 'marked') return isQuestionMarked(q);
    return true;
  });

  // Calculate line numbers for current code
  const currentCodeLines = (answers[currentQ?.id]?.code || '').split('\n');
  const lineCount = Math.max(currentCodeLines.length, 24);
  const lineNumbersArray = Array.from({ length: lineCount }, (_, i) => i + 1);

  const currentExecution = codeExecution[currentQ?.id] || {};
  const runResult = currentExecution.runResult;
  const submitResult = currentExecution.submitResult;

  return (
    <div className="exam-layout">
      {/* Non-intrusive In-App Toast */}
      {toast && (
        <div className={`in-app-toast ${toast.type === 'error' ? 'toast-error' : 'toast-success'}`}>
          {toast.type === 'error' ? <XCircle size={18} color="#f87171" /> : <CheckCircle2 size={18} color="#4ade80" />}
          <span>{toast.message}</span>
        </div>
      )}

      {/* Top Fixed Header */}
      <header className="exam-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <span style={{ fontWeight: 700, fontSize: 16 }}>{examData.test.title}</span>
          <span className="badge badge-slate" style={{ fontFamily: 'var(--font-mono)' }}>
            {examData.test.testId}
          </span>
          <span className="badge badge-blue" style={{ fontSize: 11 }}>
            Candidate: {examData.registration?.formData?.fullName || 'Exam Session'}
          </span>
        </div>

        {/* Global Synchronized Countdown Timer & Workspace Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          {violationsCount > 0 && (
            <span className="badge badge-amber" style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <AlertTriangle size={13} />
              {violationsCount} Warning Logged
            </span>
          )}

          {/* AI Proctoring Live HUD Toggle */}
          <button
            type="button"
            onClick={() => setShowAiHud(!showAiHud)}
            className="btn btn-secondary btn-sm"
            style={{
              background: aiProctorActive ? 'rgba(34, 197, 94, 0.15)' : '#1e293b',
              color: aiProctorActive ? '#4ade80' : '#94a3b8',
              borderColor: aiProctorActive ? 'rgba(34, 197, 94, 0.4)' : '#334155',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
            title={showAiHud ? 'Hide AI Monitor HUD' : 'Show AI Monitor HUD'}
          >
            <ShieldCheck size={14} />
            <span>AI Proctor: {aiProctorActive ? 'Active' : 'Offline'}</span>
          </button>

          {/* Toggle Sidebar Collapse to give Coding workspace maximum screen */}
          <button
            type="button"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="btn btn-secondary btn-sm"
            style={{ background: '#1e293b', color: '#cbd5e1', borderColor: '#334155' }}
            title={sidebarCollapsed ? 'Show Question Palette Sidebar' : 'Hide Question Palette Sidebar for Wide Code View'}
          >
            {sidebarCollapsed ? <PanelRightOpen size={14} /> : <PanelRightClose size={14} />}
            <span>{sidebarCollapsed ? 'Show Palette' : 'Hide Palette'}</span>
          </button>

          <div className={`exam-timer ${secondsRemaining !== null && secondsRemaining < 300 ? 'urgent' : ''}`}>
            <Clock size={16} />
            <span>{formatTimer(secondsRemaining)}</span>
          </div>

          <button
            type="button"
            onClick={() => setShowSubmitModal(true)}
            className="btn btn-primary btn-sm"
          >
            <Send size={15} />
            <span>Final Submit</span>
          </button>
        </div>
      </header>

      {/* Real-time AI Proctoring Violation Notification Banner */}
      {activeAiAlert && (
        <div
          style={{
            background: '#dc2626',
            color: '#ffffff',
            padding: '10px 20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontWeight: 600,
            fontSize: 13,
            zIndex: 9999,
            boxShadow: '0 4px 12px rgba(220, 38, 38, 0.35)',
            borderBottom: '2px solid #b91c1c',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <AlertTriangle size={18} />
            <span>
              <strong>AI PROCTORING ALERT:</strong> {activeAiAlert.message} — Infraction logged to examiner report!
            </span>
          </div>
          <button
            type="button"
            onClick={() => setActiveAiAlert(null)}
            style={{ background: 'none', border: 'none', color: '#ffffff', cursor: 'pointer', fontSize: 16 }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Exam Body: Question Workspace + Navigation Sidebar */}
      <div className={`exam-body ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
        {/* Main Question Panel */}
        <main className="exam-main" style={{ padding: currentQ?.questionType === 'coding' ? 14 : 24 }}>
          {currentQ && (
            <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
              {/* Question Sub-Header Bar */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span className="badge badge-slate" style={{ fontSize: 13, fontWeight: 700 }}>
                    Question {currentIndex + 1} of {questions.length}
                  </span>
                  <span className={`badge ${currentQ.questionType === 'mcq' ? 'badge-blue' : 'badge-green'}`}>
                    {currentQ.questionType === 'mcq' ? 'Multiple Choice' : 'Coding Challenge (Judge0 / Multi-Language)'}
                  </span>
                  {isQuestionAnswered(currentQ) && (
                    <span className="badge badge-green" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <CheckCheck size={13} /> Answered
                    </span>
                  )}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  {/* Layout selector for coding questions */}
                  {currentQ.questionType === 'coding' && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4, background: '#f1f5f9', padding: 2, borderRadius: 6 }}>
                      <button
                        type="button"
                        onClick={() => setSplitLayout('standard')}
                        className={`palette-filter-btn ${splitLayout === 'standard' ? 'active' : ''}`}
                        title="Standard Split (40 / 60)"
                      >
                        40/60
                      </button>
                      <button
                        type="button"
                        onClick={() => setSplitLayout('wide')}
                        className={`palette-filter-btn ${splitLayout === 'wide' ? 'active' : ''}`}
                        title="Wide Editor (25 / 75)"
                      >
                        Wide
                      </button>
                      <button
                        type="button"
                        onClick={() => setSplitLayout('equal')}
                        className={`palette-filter-btn ${splitLayout === 'equal' ? 'active' : ''}`}
                        title="Equal Split (50 / 50)"
                      >
                        50/50
                      </button>
                      <button
                        type="button"
                        onClick={() => setSplitLayout('focus')}
                        className={`palette-filter-btn ${splitLayout === 'focus' ? 'active' : ''}`}
                        title="Code Only (Hide Problem Pane)"
                      >
                        Code Only
                      </button>
                    </div>
                  )}

                  <button
                    type="button"
                    onClick={() => toggleMarkForReview(currentQ.id)}
                    className={`btn btn-sm ${isQuestionMarked(currentQ) ? 'btn-primary' : 'btn-secondary'}`}
                    style={{
                      background: isQuestionMarked(currentQ) ? '#7c3aed' : undefined,
                      borderColor: isQuestionMarked(currentQ) ? '#6d28d9' : undefined,
                    }}
                  >
                    <Bookmark size={13} />
                    <span>{isQuestionMarked(currentQ) ? 'Marked for Review' : 'Mark for Review'}</span>
                  </button>

                  <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text-secondary)' }}>
                    Marks: <span style={{ color: 'var(--text-primary)' }}>{currentQ.marks}</span>
                  </div>
                </div>
              </div>

              {/* MCQ QUESTION VIEW */}
              {currentQ.questionType === 'mcq' && (
                <div style={{ flex: 1 }}>
                  <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 20, color: 'var(--text-primary)', lineHeight: 1.5 }}>
                    {currentQ.questionText}
                  </h2>

                  <div style={{ marginTop: 16 }}>
                    {currentQ.options?.map((opt, optIndex) => {
                      const isSelected = answers[currentQ.id]?.selectedOption === optIndex;
                      return (
                        <div
                          key={optIndex}
                          className={`mcq-option ${isSelected ? 'selected' : ''}`}
                          onClick={() => handleSelectMcq(currentQ.id, optIndex)}
                        >
                          <input
                            type="radio"
                            name={`mcq_${currentQ.id}`}
                            className="mcq-radio"
                            checked={isSelected}
                            onChange={() => handleSelectMcq(currentQ.id, optIndex)}
                          />
                          <div style={{ flex: 1, fontSize: 14.5, color: 'var(--text-primary)' }}>
                            <strong>{String.fromCharCode(65 + optIndex)}.</strong> {opt}
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {answers[currentQ.id]?.selectedOption !== null && answers[currentQ.id]?.selectedOption !== undefined && (
                    <div style={{ marginTop: 16 }}>
                      <button
                        type="button"
                        onClick={() => handleClearMcq(currentQ.id)}
                        className="btn btn-secondary btn-sm"
                      >
                        Clear Selection
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* LEETCODE CODING WORKSPACE */}
              {currentQ.questionType === 'coding' && (
                <div className={`leetcode-workspace layout-${splitLayout}`}>
                  {/* Left Pane: Problem Description, Formatted Examples, Constraints */}
                  <div className="lc-problem-pane">
                    <div>
                      <h3 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>
                        {currentQ.questionText}
                      </h3>
                      <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                        <span className="badge badge-green" style={{ fontSize: 11 }}>
                          Score: {currentQ.marks} pts
                        </span>
                        <span className="badge badge-slate" style={{ fontSize: 11 }}>
                          Standard I/O
                        </span>
                      </div>
                    </div>

                    {/* Problem Description */}
                    <div style={{ fontSize: 14, lineHeight: 1.6, color: 'var(--text-primary)', whiteSpace: 'pre-wrap' }}>
                      {currentQ.description || currentQ.questionText}
                    </div>

                    {/* Sample Test Cases Formatted as LeetCode Examples */}
                    {currentQ.sampleTestCases && currentQ.sampleTestCases.length > 0 && (
                      <div>
                        <h4 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 8, textTransform: 'uppercase' }}>
                          Examples
                        </h4>
                        {currentQ.sampleTestCases.map((tc, idx) => (
                          <div key={idx} className="lc-example-card">
                            <div className="lc-example-label">Example {idx + 1}</div>
                            <div style={{ fontSize: 12.5, color: 'var(--text-secondary)', marginBottom: 2 }}>
                              <strong>Input:</strong>
                            </div>
                            <pre className="lc-code-badge">{tc.input || '[No stdin input]'}</pre>

                            <div style={{ fontSize: 12.5, color: 'var(--text-secondary)', marginBottom: 2 }}>
                              <strong>Output:</strong>
                            </div>
                            <pre className="lc-code-badge">{tc.expectedOutput}</pre>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Constraints */}
                    <div className="lc-constraints-box">
                      <div style={{ fontWeight: 700, marginBottom: 4, color: 'var(--text-primary)' }}>
                        Constraints & Execution Limits:
                      </div>
                      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, lineHeight: 1.6 }}>
                        <li>Time Limit: <strong>2.0 seconds</strong> per test case</li>
                        <li>Memory Limit: <strong>256 MB</strong></li>
                        <li>Read all inputs from standard input (stdin)</li>
                        <li>Print only the required answer to standard output (stdout)</li>
                        <li>Submitting solution runs against all hidden test cases</li>
                      </ul>
                    </div>
                  </div>

                  {/* Right Pane: LeetCode Code Workspace & Console */}
                  <div className={`lc-code-pane ${isFullscreenEditor ? 'fullscreen-editor' : ''}`}>
                    {/* Editor Toolbar */}
                    <div className="lc-toolbar">
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <Code2 size={15} color="#60a5fa" />
                        <span style={{ fontSize: 12.5, fontWeight: 600 }}>Language:</span>
                        <select
                          value={answers[currentQ.id]?.language || 'javascript'}
                          onChange={(e) => handleLanguageChange(currentQ.id, e.target.value)}
                        >
                          <option value="javascript">JavaScript (Node.js)</option>
                          <option value="python">Python 3</option>
                          <option value="cpp">C++ (GCC)</option>
                          <option value="java">Java (OpenJDK)</option>
                        </select>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        {/* Toggle Fullscreen Editor */}
                        <button
                          type="button"
                          onClick={() => setIsFullscreenEditor(!isFullscreenEditor)}
                          className="btn btn-secondary btn-sm"
                          style={{ padding: '3px 8px', fontSize: 11, background: '#27272a', color: '#d4d4d8', borderColor: '#3f3f46' }}
                          title={isFullscreenEditor ? 'Exit Fullscreen Editor' : 'Full Screen Editor Mode'}
                        >
                          {isFullscreenEditor ? <Minimize2 size={12} color="#60a5fa" /> : <Maximize2 size={12} />}
                          <span>{isFullscreenEditor ? 'Exit Fullscreen' : 'Full Screen'}</span>
                        </button>

                        <button
                          type="button"
                          onClick={() => handleCopyCode(answers[currentQ.id]?.code)}
                          className="btn btn-secondary btn-sm"
                          style={{ padding: '3px 8px', fontSize: 11, background: '#27272a', color: '#d4d4d8', borderColor: '#3f3f46' }}
                          title="Copy Code"
                        >
                          {copiedCode ? <Check size={12} color="#4ade80" /> : <Copy size={12} />}
                          <span>{copiedCode ? 'Copied' : 'Copy'}</span>
                        </button>

                        <button
                          type="button"
                          onClick={() => handleResetTemplate(currentQ.id)}
                          className="btn btn-secondary btn-sm"
                          style={{ padding: '3px 8px', fontSize: 11, background: '#27272a', color: '#d4d4d8', borderColor: '#3f3f46' }}
                          title="Reset to default language boilerplate"
                        >
                          <RotateCcw size={12} />
                          <span>Reset</span>
                        </button>
                      </div>
                    </div>

                    {/* Code Editor with Line Numbers */}
                    <div className="lc-editor-workspace">
                      <div className="lc-line-numbers">
                        {lineNumbersArray.map((n) => (
                          <div key={n}>{n}</div>
                        ))}
                      </div>

                      <textarea
                        ref={textareaRef}
                        className="lc-textarea code-textarea"
                        value={answers[currentQ.id]?.code || ''}
                        onChange={(e) => handleCodeChange(currentQ.id, e.target.value)}
                        onKeyDown={(e) => handleEditorKeyDown(e, currentQ.id)}
                        spellCheck={false}
                        autoCapitalize="off"
                        autoComplete="off"
                        autoCorrect="off"
                        placeholder="// Write your code solution here..."
                      />
                    </div>

                    {/* LeetCode Bottom Console Drawer */}
                    <div className={`lc-console ${consoleHeightMode}`}>
                      {/* Console Drawer Header */}
                      <div className="lc-console-header">
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <button
                            type="button"
                            className={`lc-tab-btn ${activeConsoleTab === 'testcase' ? 'active' : ''}`}
                            onClick={() => {
                              setActiveConsoleTab('testcase');
                              if (consoleHeightMode === 'collapsed') setConsoleHeightMode('normal');
                            }}
                          >
                            Testcase
                          </button>

                          <button
                            type="button"
                            className={`lc-tab-btn ${activeConsoleTab === 'run_result' ? 'active' : ''}`}
                            onClick={() => {
                              setActiveConsoleTab('run_result');
                              if (consoleHeightMode === 'collapsed') setConsoleHeightMode('normal');
                            }}
                          >
                            Run Result {runResult ? (runResult.passed ? '✅' : '❌') : ''}
                          </button>

                          <button
                            type="button"
                            className={`lc-tab-btn ${activeConsoleTab === 'submit_result' ? 'active' : ''}`}
                            onClick={() => {
                              setActiveConsoleTab('submit_result');
                              if (consoleHeightMode === 'collapsed') setConsoleHeightMode('expanded');
                            }}
                          >
                            Submit Result {submitResult ? (submitResult.status === 'Accepted' ? '🎉' : '⚠️') : ''}
                          </button>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <button
                            type="button"
                            onClick={() =>
                              setConsoleHeightMode((prev) =>
                                prev === 'expanded' ? 'normal' : prev === 'normal' ? 'expanded' : 'normal'
                              )
                            }
                            style={{ background: 'none', border: 'none', color: '#a1a1aa', fontSize: 11, cursor: 'pointer' }}
                          >
                            {consoleHeightMode === 'expanded' ? 'Standard Height' : 'Expand Height'}
                          </button>

                          <button
                            type="button"
                            onClick={() =>
                              setConsoleHeightMode((prev) => (prev === 'collapsed' ? 'normal' : 'collapsed'))
                            }
                            style={{ background: 'none', border: 'none', color: '#a1a1aa', fontSize: 11, cursor: 'pointer' }}
                          >
                            {consoleHeightMode === 'collapsed' ? 'Open Console ▲' : 'Minimize ▼'}
                          </button>
                        </div>
                      </div>

                      {/* Console Drawer Body */}
                      {consoleHeightMode !== 'collapsed' && (
                        <div className="lc-console-body">
                          {/* TAB 1: TESTCASE INPUT */}
                          {activeConsoleTab === 'testcase' && (
                            <div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
                                {(currentQ.sampleTestCases || []).map((_, tcIdx) => (
                                  <button
                                    key={tcIdx}
                                    type="button"
                                    className={`lc-case-pill ${selectedTestCaseIndex === tcIdx ? 'active' : ''}`}
                                    onClick={() => setSelectedTestCaseIndex(tcIdx)}
                                  >
                                    Case {tcIdx + 1}
                                  </button>
                                ))}
                                <button
                                  type="button"
                                  className={`lc-case-pill ${selectedTestCaseIndex === -1 ? 'active' : ''}`}
                                  onClick={() => setSelectedTestCaseIndex(-1)}
                                >
                                  + Custom Input
                                </button>
                              </div>

                              {selectedTestCaseIndex === -1 ? (
                                <div>
                                  <div style={{ fontSize: 11.5, color: '#a1a1aa', marginBottom: 4 }}>Custom Stdin Input:</div>
                                  <textarea
                                    className="form-control"
                                    rows={3}
                                    value={customStdin}
                                    onChange={(e) => setCustomStdin(e.target.value)}
                                    placeholder="Enter custom input string..."
                                    style={{
                                      background: '#141416',
                                      color: '#f4f4f5',
                                      fontFamily: 'var(--font-mono)',
                                      fontSize: 12,
                                      borderColor: '#3f3f46',
                                    }}
                                  />
                                </div>
                              ) : (
                                <div>
                                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                                    <div>
                                      <div style={{ fontSize: 11.5, color: '#a1a1aa', marginBottom: 4 }}>Input:</div>
                                      <div style={{ background: '#141416', padding: '8px 10px', borderRadius: 4, border: '1px solid #27272a', whiteSpace: 'pre-wrap' }}>
                                        {currentQ.sampleTestCases && currentQ.sampleTestCases[selectedTestCaseIndex]?.input || '[Empty stdin]'}
                                      </div>
                                    </div>
                                    <div>
                                      <div style={{ fontSize: 11.5, color: '#a1a1aa', marginBottom: 4 }}>Expected Output:</div>
                                      <div style={{ background: '#141416', padding: '8px 10px', borderRadius: 4, border: '1px solid #27272a', whiteSpace: 'pre-wrap' }}>
                                        {currentQ.sampleTestCases && currentQ.sampleTestCases[selectedTestCaseIndex]?.expectedOutput || '[Empty]'}
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              )}
                            </div>
                          )}

                          {/* TAB 2: SAMPLE RUN RESULT */}
                          {activeConsoleTab === 'run_result' && (
                            <div>
                              {!runResult ? (
                                <div style={{ color: '#71717a', textAlign: 'center', padding: '16px 0', fontSize: 12.5 }}>
                                  Click <strong>Run Code</strong> below to test against the selected sample input.
                                </div>
                              ) : (
                                <div className="code-output-terminal">
                                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                      {runResult.passed ? (
                                        <span className="badge badge-green" style={{ fontSize: 13, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 4 }}>
                                          <CheckCircle2 size={14} /> Sample Passed
                                        </span>
                                      ) : (
                                        <span className="badge badge-red" style={{ fontSize: 13, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 4 }}>
                                          <XCircle size={14} /> {runResult.status || 'Wrong Answer'}
                                        </span>
                                      )}
                                      <span style={{ fontSize: 12, color: '#a1a1aa' }}>
                                        Runtime: {runResult.executionTime || 'N/A'}
                                      </span>
                                    </div>
                                  </div>

                                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, fontSize: 12 }}>
                                    <div>
                                      <div style={{ color: '#a1a1aa', marginBottom: 3 }}>Your Output:</div>
                                      <div style={{ background: '#141416', padding: 8, borderRadius: 4, border: '1px solid #27272a', whiteSpace: 'pre-wrap' }}>
                                        {runResult.stdout || '[No stdout output]'}
                                      </div>
                                    </div>
                                    <div>
                                      <div style={{ color: '#a1a1aa', marginBottom: 3 }}>Expected Output:</div>
                                      <div style={{ background: '#141416', padding: 8, borderRadius: 4, border: '1px solid #27272a', whiteSpace: 'pre-wrap' }}>
                                        {runResult.expectedOutput || '[Custom Input / No Target]'}
                                      </div>
                                    </div>
                                  </div>

                                  {runResult.stderr && (
                                    <div style={{ marginTop: 10 }}>
                                      <div style={{ color: '#f87171', marginBottom: 3 }}>Error Details / Stderr:</div>
                                      <div style={{ background: '#261417', color: '#fca5a5', padding: 8, borderRadius: 4, border: '1px solid #7f1d1d', whiteSpace: 'pre-wrap', fontSize: 11.5 }}>
                                        {runResult.stderr}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          )}

                          {/* TAB 3: SUBMIT RESULT (EVALUATES AGAINST ALL TEST CASES INCLUDING HIDDEN) */}
                          {activeConsoleTab === 'submit_result' && (
                            <div>
                              {!submitResult ? (
                                <div style={{ color: '#71717a', textAlign: 'center', padding: '16px 0', fontSize: 12.5 }}>
                                  Click <strong>Submit Code</strong> to evaluate your solution against <strong>all test cases (including hidden)</strong>.
                                </div>
                              ) : (
                                <div>
                                  {/* Big Result Banner */}
                                  <div className="lc-submission-summary">
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                      {submitResult.status === 'Accepted' ? (
                                        <span className="badge badge-green" style={{ fontSize: 14, fontWeight: 700, padding: '6px 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
                                          <CheckCheck size={16} /> Accepted
                                        </span>
                                      ) : (
                                        <span className="badge badge-red" style={{ fontSize: 14, fontWeight: 700, padding: '6px 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
                                          <XCircle size={16} /> {submitResult.status}
                                        </span>
                                      )}
                                      <span style={{ fontSize: 13, color: '#f4f4f5', fontWeight: 600 }}>
                                        {submitResult.passedCases} / {submitResult.totalCases} Test Cases Passed
                                      </span>
                                    </div>

                                    <div style={{ fontSize: 12, color: '#a1a1aa' }}>
                                      Avg Runtime: <strong>{submitResult.executionTime}</strong>
                                    </div>
                                  </div>

                                  {/* Detailed list of all test cases (both public & hidden) */}
                                  <div style={{ marginTop: 8 }}>
                                    {(submitResult.results || []).map((resItem) => (
                                      <div key={resItem.caseIndex} className="lc-testcase-item">
                                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                                          <span style={{ fontWeight: 600, fontSize: 12.5, color: '#e4e4e7' }}>
                                            Testcase #{resItem.caseIndex}{' '}
                                            {resItem.isHidden && (
                                              <span className="badge badge-slate" style={{ fontSize: 10, marginLeft: 6 }}>
                                                Hidden Testcase
                                              </span>
                                            )}
                                          </span>
                                          <span
                                            className={`badge ${resItem.passed ? 'badge-green' : 'badge-red'}`}
                                            style={{ fontSize: 11 }}
                                          >
                                            {resItem.passed ? 'Passed ✓' : 'Failed ✗'} ({resItem.executionTime})
                                          </span>
                                        </div>

                                        {!resItem.isHidden ? (
                                          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, fontSize: 11.5, marginTop: 6 }}>
                                            <div style={{ background: '#18181b', padding: 6, borderRadius: 4 }}>
                                              <span style={{ color: '#a1a1aa' }}>Input:</span> {resItem.input}
                                            </div>
                                            <div style={{ background: '#18181b', padding: 6, borderRadius: 4 }}>
                                              <span style={{ color: '#a1a1aa' }}>Expected:</span> {resItem.expectedOutput}
                                            </div>
                                            <div style={{ background: '#18181b', padding: 6, borderRadius: 4 }}>
                                              <span style={{ color: '#a1a1aa' }}>Output:</span> {resItem.actualOutput || '[None]'}
                                            </div>
                                          </div>
                                        ) : (
                                          <div style={{ fontSize: 11.5, color: resItem.passed ? '#4ade80' : '#fca5a5', marginTop: 4 }}>
                                            {resItem.passed
                                              ? '✓ Hidden test case passed successfully.'
                                              : '✗ Failed on this hidden test case. Review constraints and edge cases.'}
                                          </div>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Action Bar with Run Code and Submit Code buttons */}
                      <div className="lc-action-bar">
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <span style={{ color: '#71717a', fontSize: 11.5 }}>
                            {answers[currentQ.id]?.isSavedByUser ? '✓ Solution saved' : 'Unsaved edits'}
                          </span>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          {/* Run Code button (tests sample input) */}
                          <button
                            type="button"
                            onClick={() => handleRunCode(currentQ)}
                            className="btn btn-secondary btn-sm"
                            disabled={runningCode || submittingCode}
                            style={{ background: '#27272a', color: '#ffffff', borderColor: '#3f3f46' }}
                          >
                            <Play size={13} color="#60a5fa" />
                            <span>{runningCode ? 'Running...' : 'Run Code'}</span>
                          </button>

                          {/* Submit Code button (tests ALL test cases including hidden ones just like LeetCode) */}
                          <button
                            type="button"
                            onClick={() => handleSubmitCode(currentQ)}
                            className="btn btn-primary btn-sm"
                            disabled={runningCode || submittingCode}
                            style={{ background: '#16a34a', borderColor: '#15803d' }}
                          >
                            <CheckCheck size={14} />
                            <span>{submittingCode ? 'Evaluating All Cases...' : 'Submit Code'}</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Sticky Exam Bottom Navigation Bar */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 16, paddingTop: 14, borderTop: '1px solid var(--border-color)' }}>
                <button
                  type="button"
                  onClick={() => setCurrentIndex(Math.max(0, currentIndex - 1))}
                  disabled={currentIndex === 0}
                  className="btn btn-secondary"
                >
                  <ChevronLeft size={16} />
                  <span>Previous</span>
                </button>

                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  {currentIndex < questions.length - 1 ? (
                    <button
                      type="button"
                      onClick={() => setCurrentIndex(currentIndex + 1)}
                      className="btn btn-primary"
                    >
                      <span>Next Question</span>
                      <ChevronRight size={16} />
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setShowSubmitModal(true)}
                      className="btn btn-primary"
                    >
                      <span>Review & Final Submit</span>
                      <Send size={16} />
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}
        </main>

        {/* Sidebar: Question Palette & Progress */}
        <aside className="exam-sidebar">
          {/* Progress Card */}
          <div className="card" style={{ padding: 16 }}>
            <h4 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>
              Exam Progress
            </h4>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
              <span style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)' }}>
                {answeredCount}
              </span>
              <span style={{ color: 'var(--text-muted)', fontSize: 14 }}>
                of {questions.length} answered
              </span>
            </div>
            <div
              style={{
                width: '100%',
                height: 6,
                backgroundColor: 'var(--border-color)',
                borderRadius: 999,
                marginTop: 8,
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  height: '100%',
                  width: `${(answeredCount / Math.max(1, questions.length)) * 100}%`,
                  backgroundColor: '#16a34a',
                  transition: 'width 0.3s ease',
                }}
              />
            </div>
          </div>

          {/* Question Palette Card */}
          <div className="card" style={{ padding: 16 }}>
            <h4 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 10 }}>
              Question Palette
            </h4>

            {/* Palette Filters */}
            <div className="palette-filter-group">
              <button
                type="button"
                className={`palette-filter-btn ${paletteFilter === 'all' ? 'active' : ''}`}
                onClick={() => setPaletteFilter('all')}
              >
                All ({questions.length})
              </button>
              <button
                type="button"
                className={`palette-filter-btn ${paletteFilter === 'answered' ? 'active' : ''}`}
                onClick={() => setPaletteFilter('answered')}
              >
                Ans ({answeredCount})
              </button>
              <button
                type="button"
                className={`palette-filter-btn ${paletteFilter === 'unanswered' ? 'active' : ''}`}
                onClick={() => setPaletteFilter('unanswered')}
              >
                Left ({unansweredCount})
              </button>
              <button
                type="button"
                className={`palette-filter-btn ${paletteFilter === 'marked' ? 'active' : ''}`}
                onClick={() => setPaletteFilter('marked')}
              >
                Mark ({markedCount})
              </button>
            </div>

            {/* Palette Grid */}
            <div className="question-palette">
              {filteredQuestions.map(({ q, idx }) => {
                const isCurrent = idx === currentIndex;
                const answered = isQuestionAnswered(q);
                const marked = isQuestionMarked(q);
                const visited = isQuestionVisited(q);

                let stateClass = 'unvisited';
                if (marked) {
                  stateClass = answered ? 'marked-answered' : 'marked';
                } else if (answered) {
                  stateClass = 'answered';
                } else if (visited) {
                  stateClass = 'visited-unanswered';
                }

                return (
                  <button
                    key={q.id || idx}
                    type="button"
                    onClick={() => setCurrentIndex(idx)}
                    className={`palette-btn ${stateClass} ${isCurrent ? 'current' : ''}`}
                    title={`Question ${idx + 1}: ${q.questionType.toUpperCase()} (${marked ? 'Marked for Review' : answered ? 'Answered' : visited ? 'Not Answered' : 'Not Visited'})`}
                  >
                    <span>{idx + 1}</span>
                  </button>
                );
              })}
            </div>

            {/* Palette Color Legend */}
            <div style={{ marginTop: 16, borderTop: '1px solid var(--border-color)', paddingTop: 12 }}>
              <div className="palette-legend-item">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div className="palette-legend-chip" style={{ background: '#16a34a', color: '#fff' }}>✓</div>
                  <span>Answered</span>
                </div>
                <strong>{answeredCount}</strong>
              </div>

              <div className="palette-legend-item">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div className="palette-legend-chip" style={{ background: '#fffbeb', border: '1.5px solid #f59e0b', color: '#b45309' }}>•</div>
                  <span>Not Answered</span>
                </div>
                <strong>{questions.filter((q) => isQuestionVisited(q) && !isQuestionAnswered(q)).length}</strong>
              </div>

              <div className="palette-legend-item">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div className="palette-legend-chip" style={{ background: '#7c3aed', color: '#fff' }}>★</div>
                  <span>Marked for Review</span>
                </div>
                <strong>{markedCount}</strong>
              </div>

              <div className="palette-legend-item">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div className="palette-legend-chip" style={{ background: '#f8fafc', border: '1px solid #cbd5e1', color: '#64748b' }}>-</div>
                  <span>Not Visited</span>
                </div>
                <strong>{questions.filter((q) => !isQuestionVisited(q)).length}</strong>
              </div>

              <div className="palette-legend-item">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div className="palette-legend-chip" style={{ border: '2px solid #2563eb', background: '#fff' }}>1</div>
                  <span>Current Question</span>
                </div>
                <span style={{ fontSize: 11, color: '#3b82f6', fontWeight: 600 }}>Active</span>
              </div>
            </div>
          </div>
        </aside>
      </div>

      {/* SINGLE WARNING MODAL (Anti-Cheating Policy) */}
      {showWarningModal && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: 460, borderColor: 'var(--danger-border)' }}>
            <div className="modal-header" style={{ background: 'var(--danger-light)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <ShieldAlert size={22} color="var(--danger)" />
                <h3 className="card-title" style={{ color: '#991b1b', fontSize: 17 }}>
                  Anti-Cheating Warning #1
                </h3>
              </div>
            </div>

            <div className="modal-body">
              <p style={{ fontSize: 14.5, lineHeight: 1.6, color: 'var(--text-primary)', marginBottom: 12 }}>
                <strong>Attention Candidate:</strong> You have exited full-screen or navigated away from the exam tab.
              </p>
              <div
                style={{
                  background: '#fef2f2',
                  border: '1px solid #fecaca',
                  padding: 12,
                  borderRadius: 'var(--radius-md)',
                  fontSize: 13,
                  color: '#991b1b',
                  marginBottom: 14,
                }}
              >
                ⚠️ <strong>CRITICAL RULE:</strong> You are granted only <strong>ONE warning</strong>. If you switch tabs
                or exit full-screen again, your exam will be <strong>AUTOMATICALLY SUBMITTED IMMEDIATELY</strong> with
                all answers locked.
              </div>
              <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                Click below to return to full-screen mode and continue your exam.
              </p>
            </div>

            <div className="modal-footer">
              <button
                type="button"
                onClick={reEnterFullscreen}
                className="btn btn-primary btn-lg"
                style={{ width: '100%' }}
              >
                <Maximize2 size={16} />
                <span>I Understand & Re-Enter Full-Screen</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Final Submit Confirmation Modal */}
      {showSubmitModal && (
        <div className="modal-backdrop" onClick={() => setShowSubmitModal(false)}>
          <div className="modal-card" style={{ maxWidth: 480 }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="card-title" style={{ fontSize: 17 }}>
                Final Exam Submission
              </h3>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setShowSubmitModal(false)}
              >
                ✕
              </button>
            </div>

            <div className="modal-body">
              <p style={{ fontSize: 14.5, marginBottom: 16 }}>
                Are you sure you want to submit your examination? Once submitted, you cannot change your responses.
              </p>

              <div
                style={{
                  background: 'var(--bg-subtle)',
                  padding: 14,
                  borderRadius: 'var(--radius-md)',
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: 12,
                  fontSize: 13.5,
                  marginBottom: 16,
                }}
              >
                <div>
                  Total Questions: <strong>{questions.length}</strong>
                </div>
                <div>
                  Questions Answered: <strong style={{ color: '#16a34a' }}>{answeredCount}</strong>
                </div>
                <div>
                  Unanswered:{' '}
                  <strong style={{ color: unansweredCount > 0 ? '#d97706' : 'inherit' }}>
                    {unansweredCount}
                  </strong>
                </div>
                <div>
                  Marked for Review: <strong>{markedCount}</strong>
                </div>
                <div>
                  Time Left: <strong>{formatTimer(secondsRemaining)}</strong>
                </div>
              </div>
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setShowSubmitModal(false)}
                disabled={submitting}
              >
                Continue Exam
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleManualSubmit}
                disabled={submitting}
              >
                <Send size={15} />
                <span>{submitting ? 'Submitting...' : 'Confirm Final Submit'}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Live Multimodal AI Proctoring HUD Floating / Docked Widget */}
      {showAiHud && (
        <div
          style={{
            position: 'fixed',
            bottom: 20,
            right: 20,
            width: aiHudMinimized ? 220 : 280,
            background: 'rgba(15, 23, 42, 0.95)',
            backdropFilter: 'blur(12px)',
            border: '1px solid rgba(59, 130, 246, 0.4)',
            borderRadius: '12px',
            boxShadow: '0 12px 32px rgba(0, 0, 0, 0.5)',
            color: '#f8fafc',
            zIndex: 900,
            overflow: 'hidden',
            transition: 'all 0.25s ease',
          }}
        >
          {/* Widget Header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '8px 12px',
              background: 'rgba(30, 41, 59, 0.8)',
              borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
              fontSize: 12,
              fontWeight: 700,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: aiProctorActive ? '#22c55e' : '#eab308',
                  boxShadow: aiProctorActive ? '0 0 8px #22c55e' : 'none',
                }}
              />
              <span>AI Proctoring HUD</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <button
                type="button"
                onClick={() => setAiHudMinimized(!aiHudMinimized)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#94a3b8',
                  cursor: 'pointer',
                  padding: 2,
                }}
                title={aiHudMinimized ? 'Expand HUD' : 'Minimize HUD'}
              >
                {aiHudMinimized ? <Maximize2 size={12} /> : <Minimize2 size={12} />}
              </button>
              <button
                type="button"
                onClick={() => setShowAiHud(false)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#94a3b8',
                  cursor: 'pointer',
                  padding: 2,
                }}
                title="Hide HUD"
              >
                ✕
              </button>
            </div>
          </div>

          {!aiHudMinimized && (
            <div style={{ padding: 10 }}>
              {/* Live Video Feed Preview */}
              <div
                style={{
                  position: 'relative',
                  width: '100%',
                  height: 140,
                  borderRadius: 8,
                  overflow: 'hidden',
                  background: '#020617',
                  border: '1px solid #1e293b',
                  marginBottom: 10,
                }}
              >
                {aiProctorActive ? (
                  <img
                    src="http://localhost:8000/api/ai/video-feed"
                    alt="AI Monitor"
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    onError={(e) => {
                      e.target.style.display = 'none';
                    }}
                  />
                ) : (
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      height: '100%',
                      color: '#64748b',
                      fontSize: 11,
                    }}
                  >
                    AI Monitor Standby
                  </div>
                )}
                {/* Live Gaze tag */}
                <div
                  style={{
                    position: 'absolute',
                    top: 6,
                    left: 6,
                    padding: '2px 6px',
                    borderRadius: 4,
                    background: 'rgba(0,0,0,0.6)',
                    fontSize: 10,
                    fontFamily: 'var(--font-mono)',
                    color: '#38bdf8',
                  }}
                >
                  Gaze: {aiTelemetry?.direction || 'CENTER'}
                </div>
              </div>

              {/* Status Telemetry Pills */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, fontSize: 11 }}>
                <div
                  style={{
                    padding: '5px 8px',
                    borderRadius: 6,
                    background: aiTelemetry?.face_verified ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                    border: `1px solid ${aiTelemetry?.face_verified ? 'rgba(34, 197, 94, 0.4)' : 'rgba(239, 68, 68, 0.4)'}`,
                    color: aiTelemetry?.face_verified ? '#4ade80' : '#f87171',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 5,
                  }}
                >
                  {aiTelemetry?.face_verified ? <UserCheck size={13} /> : <UserX size={13} />}
                  <span>Face: {aiTelemetry?.face_verified ? 'Match' : aiTelemetry?.face_detected ? 'Check' : 'Missing'}</span>
                </div>

                <div
                  style={{
                    padding: '5px 8px',
                    borderRadius: 6,
                    background: aiTelemetry?.looking_away ? 'rgba(234, 179, 8, 0.15)' : 'rgba(34, 197, 94, 0.15)',
                    border: `1px solid ${aiTelemetry?.looking_away ? 'rgba(234, 179, 8, 0.4)' : 'rgba(34, 197, 94, 0.4)'}`,
                    color: aiTelemetry?.looking_away ? '#facc15' : '#4ade80',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 5,
                  }}
                >
                  <Eye size={13} />
                  <span>{aiTelemetry?.looking_away ? 'Away' : 'Focused'}</span>
                </div>

                <div
                  style={{
                    padding: '5px 8px',
                    borderRadius: 6,
                    background: aiTelemetry?.multiple_speakers ? 'rgba(239, 68, 68, 0.15)' : 'rgba(34, 197, 94, 0.15)',
                    border: `1px solid ${aiTelemetry?.multiple_speakers ? 'rgba(239, 68, 68, 0.4)' : 'rgba(34, 197, 94, 0.4)'}`,
                    color: aiTelemetry?.multiple_speakers ? '#f87171' : '#4ade80',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 5,
                  }}
                >
                  <Mic size={13} />
                  <span>{aiTelemetry?.multiple_speakers ? 'Voices!' : 'Audio OK'}</span>
                </div>

                <div
                  style={{
                    padding: '5px 8px',
                    borderRadius: 6,
                    background: (aiTelemetry?.phone_detected || aiTelemetry?.multiple_people || aiTelemetry?.book_detected)
                      ? 'rgba(239, 68, 68, 0.2)'
                      : 'rgba(34, 197, 94, 0.15)',
                    border: `1px solid ${(aiTelemetry?.phone_detected || aiTelemetry?.multiple_people || aiTelemetry?.book_detected)
                      ? 'rgba(239, 68, 68, 0.4)'
                      : 'rgba(34, 197, 94, 0.4)'}`,
                    color: (aiTelemetry?.phone_detected || aiTelemetry?.multiple_people || aiTelemetry?.book_detected)
                      ? '#f87171'
                      : '#4ade80',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 5,
                  }}
                >
                  <Camera size={13} />
                  <span>{aiTelemetry?.phone_detected ? 'Phone!' : aiTelemetry?.multiple_people ? '2+ People!' : 'Clear'}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
