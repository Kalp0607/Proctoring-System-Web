const Registration = require('../models/Registration');
const Test = require('../models/Test');

// @desc    Get all registered students for a specific test
// @route   GET /api/tests/:testId/registrations
// @access  Private (Examiner only)
exports.getTestRegistrations = async (req, res) => {
  try {
    const test = await Test.findOne({ testId: req.params.testId.toUpperCase() });
    if (!test) {
      return res.status(404).json({ message: 'Test not found' });
    }

    // Verify examiner ownership
    if (test.examinerId.toString() !== req.user._id.toString()) {
      return res.status(403).json({ message: 'Not authorized to view registrations for this test' });
    }

    const registrations = await Registration.find({ testId: test._id })
      .populate('studentId', 'name email')
      .sort({ registeredAt: -1 });

    res.json({
      test: {
        testId: test.testId,
        title: test.title,
        registrationFields: test.registrationFields,
        requirePhoto: test.requirePhoto,
      },
      registrations,
    });
  } catch (error) {
    console.error('Get registrations error:', error);
    res.status(500).json({ message: error.message || 'Server error' });
  }
};

// @desc    Remove/disqualify a student registration from a test
// @route   DELETE /api/tests/:testId/registrations/:registrationId
// @access  Private (Examiner only)
exports.removeStudentFromTest = async (req, res) => {
  try {
    const test = await Test.findOne({ testId: req.params.testId.toUpperCase() });
    if (!test) {
      return res.status(404).json({ message: 'Test not found' });
    }

    if (test.examinerId.toString() !== req.user._id.toString()) {
      return res.status(403).json({ message: 'Not authorized to manage registrations for this test' });
    }

    const { reason } = req.body;
    const registration = await Registration.findById(req.params.registrationId);

    if (!registration) {
      return res.status(404).json({ message: 'Registration record not found' });
    }

    registration.isRemoved = true;
    registration.removalReason = reason || 'Removed by Examiner';
    await registration.save();

    res.json({
      success: true,
      message: 'Student removed from test successfully',
      registration,
    });
  } catch (error) {
    console.error('Remove student error:', error);
    res.status(500).json({ message: error.message || 'Server error' });
  }
};
