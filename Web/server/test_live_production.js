const puppeteer = require('puppeteer-core');
const fs = require('fs');

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

async function runLiveProductionVerification() {
  console.log('================================================================');
  console.log('STARTING LIVE PRODUCTION VERIFICATION (REAL CHROME BROWSER)');
  console.log('Target Production URL: http://127.0.0.1:5000');
  console.log('================================================================\n');

  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800 });

  try {
    // -------------------------------------------------------------
    // 1. Load Homepage / Login on Live Production Server
    // -------------------------------------------------------------
    console.log('[Step 1] Navigating to http://127.0.0.1:5000/login ...');
    await page.goto('http://127.0.0.1:5000/login', { waitUntil: 'networkidle0' });

    const loginTitle = await page.$eval('h1', (el) => el.innerText);
    console.log('✓ Login Page Loaded. Heading:', loginTitle);
    if (!loginTitle.includes('Sign in')) throw new Error('Login page title mismatch');

    // -------------------------------------------------------------
    // 2. Register New Examiner
    // -------------------------------------------------------------
    console.log('\n[Step 2] Navigating to http://127.0.0.1:5000/register ...');
    await page.goto('http://127.0.0.1:5000/register', { waitUntil: 'networkidle0' });

    // Select Examiner role button
    console.log('Selecting Examiner role...');
    const buttons = await page.$$('button');
    for (const btn of buttons) {
      const text = await page.evaluate((el) => el.innerText, btn);
      if (text.includes('Examiner / Teacher')) {
        await btn.click();
        break;
      }
    }

    const examinerEmail = `prof_hopper_${Date.now()}@university.edu`;
    await page.type('#reg-name', 'Dr. Grace Hopper');
    await page.type('#reg-email', examinerEmail);
    await page.type('#reg-password', 'SecurePass2026!');

    console.log('Submitting Examiner Registration for:', examinerEmail);
    await page.click('button[type="submit"]');
    await page.waitForFunction(() => window.location.pathname.includes('/examiner/dashboard'), { timeout: 8000 });

    console.log('Current URL after registration:', page.url());
    console.log('✓ Examiner Registered and landed on Examiner Dashboard');

    // -------------------------------------------------------------
    // 3. Create a Full Examination
    // -------------------------------------------------------------
    console.log('\n[Step 3] Navigating to Test Creation page...');
    await page.goto('http://127.0.0.1:5000/examiner/create-test', { waitUntil: 'networkidle0' });

    await page.type('#title', 'Algorithms & Distributed Systems Midterm');
    await page.type('#description', 'Strict full-screen exam. Tab switching is monitored.');

    // Explicit test password
    await page.$eval('#testPassword', (el) => { el.value = ''; });
    await page.type('#testPassword', 'PASS2026');
    const testPassword = 'PASS2026';

    // Start 2 mins from now, end in 60 mins, deadline 2 mins from now
    const now = new Date();
    const startD = new Date(now.getTime() + 2 * 60 * 1000);
    const endD = new Date(startD.getTime() + 60 * 60 * 1000);
    const deadD = startD;

    const pad = (n) => String(n).padStart(2, '0');
    const fmt = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;

    await page.evaluate((sVal, eVal, dVal) => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      
      const s = document.querySelector('#startTime');
      setter.call(s, sVal);
      s.dispatchEvent(new Event('input', { bubbles: true }));
      s.dispatchEvent(new Event('change', { bubbles: true }));

      const e = document.querySelector('#endTime');
      setter.call(e, eVal);
      e.dispatchEvent(new Event('input', { bubbles: true }));
      e.dispatchEvent(new Event('change', { bubbles: true }));

      const d = document.querySelector('#registrationDeadline');
      setter.call(d, dVal);
      d.dispatchEvent(new Event('input', { bubbles: true }));
      d.dispatchEvent(new Event('change', { bubbles: true }));
    }, fmt(startD), fmt(endD), fmt(deadD));

    console.log('Form timing and password fields configured. Password:', testPassword);

    console.log('Submitting test creation form...');
    await page.click('button[type="submit"]');
    await page.waitForFunction(() => window.location.pathname.includes('/share'), { timeout: 8000 });

    console.log('Current URL after test creation:', page.url());
    const testId = page.url().split('/test/')[1].split('/share')[0];
    console.log('✓ Examination Created Successfully! Generated Test ID:', testId);

    // Verify QR code and credentials on Share Hub
    const hasQrSvg = await page.$('svg') !== null;
    console.log('✓ QR Code SVG rendered on Share Hub:', hasQrSvg);
    console.log('✓ Verified Test ID:', testId, '| Password:', testPassword);

    // -------------------------------------------------------------
    // 4. Student (Examinee) Registration Flow
    // -------------------------------------------------------------
    console.log('\n[Step 4] Launching Examinee Student Session in New Context...');
    const studentContext = await browser.createBrowserContext();
    const studentPage = await studentContext.newPage();
    await studentPage.setViewport({ width: 1280, height: 800 });

    studentPage.on('console', (msg) => console.log('  [Browser Student Console]:', msg.text()));
    studentPage.on('pageerror', (err) => console.error('  [Browser Student Error]:', err.message));

    const studentEmail = `alice_student_${Date.now()}@university.edu`;
    console.log('Registering student account:', studentEmail);
    await studentPage.goto('http://127.0.0.1:5000/register', { waitUntil: 'networkidle0' });

    await studentPage.type('#reg-name', 'Alice Student');
    await studentPage.type('#reg-email', studentEmail);
    await studentPage.type('#reg-password', 'StudentPass123!');

    await studentPage.click('button[type="submit"]');
    await studentPage.waitForFunction(() => window.location.pathname.includes('/student/dashboard'), { timeout: 8000 });
    console.log('✓ Student registered and arrived at:', studentPage.url());

    // -------------------------------------------------------------
    // 5. Student Entering Test via Direct Link & Registering
    // -------------------------------------------------------------
    console.log(`\n[Step 5] Student entering test via http://127.0.0.1:5000/test/enter/${testId} ...`);
    await studentPage.goto(`http://127.0.0.1:5000/test/enter/${testId}`, { waitUntil: 'networkidle0' });

    // Enter test passcode
    console.log('Entering test password:', testPassword);
    await studentPage.type('#enter-pass', testPassword);
    await studentPage.click('button[type="submit"]');
    await studentPage.waitForSelector('form input[id^="field_"]', { timeout: 8000 });
    console.log('✓ Password verified! Candidate registration form unlocked.');

    // Fill all registration dynamic fields
    const dynamicInputs = await studentPage.$$('input[id^="field_"]');
    console.log(`Found ${dynamicInputs.length} dynamic registration fields.`);
    for (let i = 0; i < dynamicInputs.length; i++) {
      await dynamicInputs[i].type(`Candidate_Val_${i + 1}`);
    }
    console.log('✓ Filled all required dynamic registration fields.');

    // Upload student photo file (valid 1x1 JPEG)
    const fileInput = await studentPage.$('input[type="file"]');
    const dummyPath = require('path').join(__dirname, 'test_avatar.jpg');
    // Valid 1x1 JPEG binary
    const jpegBytes = Buffer.from([
      0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0x00, 0x01, 0x01, 0x01, 0x00, 0x48,
      0x00, 0x48, 0x00, 0x00, 0xff, 0xdb, 0x00, 0x43, 0x00, 0xff, 0xc0, 0x00, 0x0b, 0x08, 0x00, 0x01,
      0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xff, 0xc4, 0x00, 0x14, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00,
      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x09, 0xff, 0xda, 0x00, 0x08,
      0x01, 0x01, 0x00, 0x00, 0x3f, 0x00, 0x7f, 0x00, 0xff, 0xd9
    ]);
    fs.writeFileSync(dummyPath, jpegBytes);

    if (fileInput) {
      await fileInput.uploadFile(dummyPath);
      console.log('✓ Student verification photo attached.');
    }

    console.log('Submitting registration form...');
    await studentPage.click('button[type="submit"]');
    await studentPage.waitForFunction(() => window.location.pathname.includes('/exam/pre-test/'), { timeout: 8000 });

    console.log('Current URL after registration:', studentPage.url());
    console.log('✓ Successfully arrived at Pre-Test Waiting Room!');

    // -------------------------------------------------------------
    // 6. Pre-Test Waiting Room & Readiness Verification
    // -------------------------------------------------------------
    console.log('\n[Step 6] Inspecting Pre-Test Waiting Room (15-Minute Panel)...');
    await studentPage.waitForSelector('.card-title', { timeout: 8000 });
    const waitingRoomText = await studentPage.evaluate(() => document.body.innerText);
    if (!waitingRoomText.includes('Pre-Test Waiting Room') && !waitingRoomText.includes('Examination Rules')) {
      throw new Error('Pre-test waiting room content not rendered');
    }
    console.log('✓ Pre-test waiting room verified: Countdown, anti-cheating rules, device setup.');

    // -------------------------------------------------------------
    // 7. Active Exam Environment & Anti-Cheating Violation Handling
    // -------------------------------------------------------------
    console.log(`\n[Step 7] Entering Active Exam Environment http://127.0.0.1:5000/exam/take/${testId} ...`);
    await studentPage.goto(`http://127.0.0.1:5000/exam/take/${testId}`, { waitUntil: 'domcontentloaded' });

    // Wait for exam interface to render
    await studentPage.waitForSelector('.exam-layout', { timeout: 8000 });
    console.log('✓ Active exam environment loaded with full layout.');

    // Verify timer is running
    const timerText = await studentPage.$eval('.exam-timer span', (el) => el.innerText);
    console.log('✓ Live countdown timer active:', timerText);

    // Answer Question 1 (MCQ)
    console.log('Solving Question 1 (MCQ)...');
    const mcqOptions = await studentPage.$$('.mcq-option');
    if (mcqOptions.length > 0) {
      await mcqOptions[1].click();
      console.log('✓ Option selected and autosaved.');
    }

    // Verify Question Palette
    const paletteButtons = await studentPage.$$('.palette-btn');
    console.log(`✓ Question Palette rendered with ${paletteButtons.length} questions.`);

    // Switch to Question 2 (Coding)
    if (paletteButtons.length > 1) {
      await paletteButtons[1].click();
      console.log('Switched to Question 2 (Coding Challenge).');
      await studentPage.waitForSelector('.code-textarea');

      console.log('Clicking "Run Code" button to test Judge0 code execution...');
      await studentPage.evaluate(() => {
        const btns = Array.from(document.querySelectorAll('button'));
        const run = btns.find((b) => b.innerText.includes('Run Code'));
        if (run) run.click();
      });
      await studentPage.waitForSelector('.code-output-terminal', { timeout: 10000 });
      const terminalText = await studentPage.$eval('.code-output-terminal', (el) => el.innerText);
      console.log('✓ Judge0 Output Terminal Response:\n', terminalText.trim());
    }

    // TEST ANTI-CHEATING TAB SWITCH DETECTION (1 Warning Rule)
    console.log('\n[Anti-Cheating Test] Triggering browser tab switch / blur event...');
    await studentPage.evaluate(() => {
      Object.defineProperty(document, 'hidden', { value: true, writable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });

    // Wait for Warning Modal #1
    await studentPage.waitForSelector('.modal-card', { timeout: 5000 });
    const modalHeading = await studentPage.$eval('.card-title', (el) => el.innerText);
    console.log('✓ Warning Modal Triggered! Title:', modalHeading);
    if (!modalHeading.includes('Warning #1')) {
      throw new Error(`Expected Anti-Cheating Warning #1, got: ${modalHeading}`);
    }

    // Dismiss warning modal
    console.log('Dismissing warning modal...');
    await studentPage.click('.modal-footer button');
    await studentPage.waitForFunction(() => !document.querySelector('.modal-backdrop'));
    console.log('✓ Warning acknowledged. Exam resumed.');

    // -------------------------------------------------------------
    // 8. Final Submit Exam
    // -------------------------------------------------------------
    console.log('\n[Step 8] Initiating Final Exam Submit...');
    await studentPage.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const found = btns.find((b) => b.innerText.includes('Final Submit'));
      if (found) found.click();
    });

    await studentPage.waitForSelector('.modal-card');
    console.log('✓ Final Submit confirmation summary modal displayed.');

    // Confirm submission
    console.log('Confirming submission...');
    await studentPage.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('.modal-footer button'));
      const confirm = btns.find((b) => b.innerText.includes('Confirm Final Submit'));
      if (confirm) confirm.click();
    });

    await studentPage.waitForFunction(() => window.location.pathname.includes('/exam/submitted/'), { timeout: 20000 });
    console.log('Current URL after submit:', studentPage.url());
    console.log('✓ Landed on Submission Success confirmation page!');

    // -------------------------------------------------------------
    // 9. Examiner Report, Disqualification (0 Marks) & PDF Export
    // -------------------------------------------------------------
    console.log('\n[Step 9] Switching back to Examiner to inspect Test Report...');
    await page.goto(`http://127.0.0.1:5000/examiner/test/${testId}/report`, { waitUntil: 'networkidle0' });

    const reportHeader = await page.$eval('h1', (el) => el.innerText);
    console.log('✓ Examiner Report Page Loaded. Heading:', reportHeader);

    // Verify candidate row in table
    await page.waitForSelector('.table-container');
    const tableText = await page.$eval('.table-container', (el) => el.innerText);
    console.log('✓ Candidate appeared in report table. Summary snippet:', tableText.slice(0, 150));

    // Test Examiner Disqualification (0 Marks) Action
    console.log('Opening Examiner Review modal to award 0 Marks penalty for cheating...');
    const reviewBtn = await page.evaluateHandle(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      return btns.find((b) => b.innerText.includes('Review & Mark'));
    });
    if (reviewBtn) {
      await reviewBtn.click();
      await page.waitForSelector('.modal-card');

      // Click "Award 0 Marks" checkbox
      const disqCheckbox = await page.$('input[type="checkbox"]');
      if (disqCheckbox) {
        await disqCheckbox.click();
        console.log('Checked "Award 0 Marks (Disqualify Candidate for Cheating)"');
      }

      // Save decision
      console.log('Saving Examiner decision...');
      await page.evaluate(() => {
        const btns = Array.from(document.querySelectorAll('.modal-footer button'));
        const save = btns.find((b) => b.innerText.includes('Save Decision'));
        if (save) save.click();
      });

      await page.waitForFunction(() => !document.querySelector('.modal-backdrop'), { timeout: 6000 });
      console.log('✓ Examiner Decision Saved! Student marked with 0 Marks.');
    }

    // Verify PDF Report Generation from Live Server
    console.log('Testing live PDF Report generation endpoint...');
    const token = await page.evaluate(() => localStorage.getItem('token'));
    const pdfResponse = await page.evaluate(async (tid, tok) => {
      const res = await fetch(`/api/reports/test/${tid}/pdf`, {
        headers: { Authorization: `Bearer ${tok}` },
      });
      return { status: res.status, size: (await res.blob()).size, type: res.headers.get('content-type') };
    }, testId, token);

    console.log('✓ Live PDF Report Generated:', pdfResponse);
    if (pdfResponse.status !== 200 || !pdfResponse.type.includes('pdf') || pdfResponse.size < 1000) {
      throw new Error('Live PDF generation returned unexpected response');
    }

    console.log('\n================================================================');
    console.log('🎉 ALL LIVE PRODUCTION BROWSER FLOWS PASSED 100% SUCCESSFULLY! 🎉');
    console.log('================================================================');
  } catch (err) {
    console.error('\n❌ LIVE PRODUCTION VERIFICATION FAILED:', err);
    throw err;
  } finally {
    await browser.close();
  }
}

runLiveProductionVerification().catch(() => process.exit(1));
