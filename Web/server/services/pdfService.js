const PDFDocument = require('pdfkit');

/**
 * Generate a clean, professional PDF test report for the Examiner
 */
function generateTestReportPDF({ test, submissions, registrations, res }) {
  const doc = new PDFDocument({ margin: 40, size: 'A4' });

  // Stream directly to response
  doc.pipe(res);

  // Colors
  const primaryColor = '#1e293b';
  const secondaryColor = '#475569';
  const accentColor = '#2563eb';
  const dangerColor = '#dc2626';
  const warningColor = '#d97706';
  const successColor = '#16a34a';
  const borderColor = '#e2e8f0';

  // Header Banner
  doc.rect(40, 40, 515, 65).fill(primaryColor);
  doc.fillColor('#ffffff').fontSize(18).font('Helvetica-Bold').text('AI-PROCTORED EXAM REPORT', 55, 52);
  doc.fontSize(10).font('Helvetica').text(`Test Title: ${test.title} | Test ID: ${test.testId}`, 55, 75);
  doc.fontSize(9).text(`Generated on: ${new Date().toLocaleString()}`, 55, 88);

  doc.moveDown(4);

  // Test Metadata Section
  doc.fillColor(primaryColor).fontSize(12).font('Helvetica-Bold').text('1. Examination Overview', 40, 120);
  doc.rect(40, 135, 515, 60).stroke(borderColor);

  doc.fillColor(secondaryColor).fontSize(9).font('Helvetica');
  doc.text(`Examiner: ${test.examinerId?.name || 'N/A'} (${test.examinerId?.email || 'N/A'})`, 50, 145);
  doc.text(`Start Time: ${new Date(test.startTime).toLocaleString()}`, 50, 160);
  doc.text(`End Time: ${new Date(test.endTime).toLocaleString()}`, 50, 175);

  doc.text(`Total Questions: ${test.questions.length}`, 300, 145);
  doc.text(`Total Marks: ${test.totalMarks}`, 300, 160);
  doc.text(`Registration Deadline: ${new Date(test.registrationDeadline).toLocaleString()}`, 300, 175);

  // Statistics Summary
  const totalRegistered = registrations.length;
  const totalAppeared = submissions.length;
  const totalDisqualified = submissions.filter((s) => s.examinerReview?.isDisqualified).length;
  const highRiskCount = submissions.filter((s) => s.proctoring?.riskLevel === 'High').length;
  const avgMarks =
    totalAppeared > 0
      ? (
          submissions.reduce(
            (sum, s) =>
              sum +
              (s.examinerReview?.isDisqualified
                ? 0
                : s.examinerReview?.finalMarks !== undefined
                ? s.examinerReview.finalMarks
                : s.totalMarksObtained || 0),
            0
          ) / totalAppeared
        ).toFixed(1)
      : '0.0';

  doc.fillColor(primaryColor).fontSize(12).font('Helvetica-Bold').text('2. Exam Statistics', 40, 210);

  const stats = [
    { label: 'Registered', val: totalRegistered },
    { label: 'Appeared', val: totalAppeared },
    { label: 'Avg Score', val: `${avgMarks}/${test.totalMarks}` },
    { label: 'High Risk', val: highRiskCount },
    { label: 'Disqualified (0 Marks)', val: totalDisqualified },
  ];

  const colWidth = 515 / stats.length;
  stats.forEach((item, idx) => {
    const x = 40 + idx * colWidth;
    doc.rect(x, 225, colWidth - 5, 45).fill('#f8fafc');
    doc.fillColor(secondaryColor).fontSize(8).font('Helvetica').text(item.label, x + 5, 232, { width: colWidth - 10, align: 'center' });
    doc.fillColor(primaryColor).fontSize(14).font('Helvetica-Bold').text(String(item.val), x + 5, 248, { width: colWidth - 10, align: 'center' });
  });

  // Candidate Results Table
  let currentY = 290;
  doc.fillColor(primaryColor).fontSize(12).font('Helvetica-Bold').text('3. Candidate Performance & Proctoring Details', 40, currentY);
  currentY += 18;

  // Table Headers
  doc.rect(40, currentY, 515, 22).fill('#f1f5f9');
  doc.fillColor(primaryColor).fontSize(8).font('Helvetica-Bold');
  doc.text('Student', 48, currentY + 6);
  doc.text('Submitted', 180, currentY + 6);
  doc.text('Score', 245, currentY + 6);
  doc.text('Risk Level', 310, currentY + 6);
  doc.text('Violations', 380, currentY + 6);
  doc.text('Status / Examiner Action', 440, currentY + 6);
  currentY += 24;

  // Render Submissions
  submissions.forEach((sub, index) => {
    // Check if new page needed
    if (currentY > 730) {
      doc.addPage();
      currentY = 40;
    }

    const isEven = index % 2 === 0;
    if (isEven) {
      doc.rect(40, currentY, 515, 30).fill('#fafafa');
    }

    const reg = registrations.find((r) => r.studentId?._id?.toString() === sub.studentId?._id?.toString());
    const regData = reg && reg.formData ? Array.from(reg.formData.entries()).map(([k, v]) => `${k}: ${v}`).join(', ') : '';

    const studentName = sub.studentId?.name || 'Unknown Student';
    const studentEmail = sub.studentId?.email || '';
    const score = sub.examinerReview?.isDisqualified
      ? '0 (Cheating)'
      : `${sub.examinerReview?.finalMarks !== undefined ? sub.examinerReview.finalMarks : sub.totalMarksObtained}/${test.totalMarks}`;

    const risk = sub.proctoring?.riskLevel || 'Low';
    const violationsCount = (sub.proctoring?.violations?.length || 0) + (sub.proctoring?.tabSwitchCount || 0);

    doc.fillColor(primaryColor).fontSize(8).font('Helvetica-Bold').text(studentName, 48, currentY + 4, { width: 125, ellipsis: true });
    doc.fillColor(secondaryColor).fontSize(7).font('Helvetica').text(studentEmail, 48, currentY + 14, { width: 125, ellipsis: true });

    doc.fillColor(secondaryColor).fontSize(8).text(sub.submittedAt ? new Date(sub.submittedAt).toLocaleTimeString() : 'In Progress', 180, currentY + 10);
    
    // Score
    if (sub.examinerReview?.isDisqualified) {
      doc.fillColor(dangerColor).font('Helvetica-Bold').text(score, 245, currentY + 10);
    } else {
      doc.fillColor(primaryColor).font('Helvetica').text(score, 245, currentY + 10);
    }

    // Risk badge text
    if (risk === 'High') doc.fillColor(dangerColor).font('Helvetica-Bold');
    else if (risk === 'Medium') doc.fillColor(warningColor).font('Helvetica-Bold');
    else doc.fillColor(successColor).font('Helvetica');
    doc.text(risk, 310, currentY + 10);

    // Violations count
    doc.fillColor(secondaryColor).font('Helvetica').text(`${violationsCount} recorded`, 380, currentY + 10);

    // Status
    if (sub.examinerReview?.isDisqualified) {
      doc.fillColor(dangerColor).font('Helvetica-Bold').text('Disqualified (0)', 440, currentY + 6);
      if (sub.examinerReview?.disqualificationReason) {
        doc.fillColor(secondaryColor).fontSize(6).font('Helvetica').text(sub.examinerReview.disqualificationReason, 440, currentY + 16, { width: 110, ellipsis: true });
      }
    } else {
      doc.fillColor(successColor).font('Helvetica').text('Cleared', 440, currentY + 10);
    }

    currentY += 32;
  });

  // Footer
  doc.fontSize(7).fillColor('#94a3b8').text(
    'End of official exam report. Verified by Anti-Proctoring Examination System.',
    40,
    780,
    { align: 'center', width: 515 }
  );

  doc.end();
}

module.exports = { generateTestReportPDF };
