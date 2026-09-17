const mongoose = require('mongoose');

const registrationSchema = new mongoose.Schema(
  {
    testId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'Test',
      required: true,
    },
    studentId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User',
      required: true,
    },
    formData: {
      type: Map,
      of: String,
      default: {},
    },
    photoUrl: {
      type: String,
      default: '',
    },
    isRemoved: {
      type: Boolean,
      default: false,
    },
    removalReason: {
      type: String,
      default: '',
    },
    registeredAt: {
      type: Date,
      default: Date.now,
    },
  },
  { timestamps: true }
);

// One registration per student per test
registrationSchema.index({ testId: 1, studentId: 1 }, { unique: true });

module.exports = mongoose.model('Registration', registrationSchema);
