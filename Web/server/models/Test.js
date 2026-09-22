const mongoose = require('mongoose');

const questionSchema = new mongoose.Schema({
  id: {
    type: String,
    required: true,
  },
  questionType: {
    type: String,
    enum: ['mcq', 'coding'],
    required: true,
  },
  questionText: {
    type: String,
    required: true,
  },
  marks: {
    type: Number,
    required: true,
    min: 1,
    default: 1,
  },
  // MCQ specific
  options: [
    {
      type: String,
    },
  ],
  correctOption: {
    type: Number, // 0-based index
  },
  // Coding specific
  description: {
    type: String,
  },
  starterCode: {
    type: String,
    default: '// Write your code here\n',
  },
  language: {
    type: String,
    default: 'javascript', // 'javascript', 'python', 'cpp', 'java'
  },
  testCases: [
    {
      input: { type: String, default: '' },
      expectedOutput: { type: String, required: true },
      isHidden: { type: Boolean, default: false },
    },
  ],
});

const registrationFieldSchema = new mongoose.Schema({
  id: { type: String, required: true },
  label: { type: String, required: true },
  fieldType: { type: String, enum: ['text', 'number', 'email'], default: 'text' },
  required: { type: Boolean, default: true },
});

const testSchema = new mongoose.Schema(
  {
    testId: {
      type: String,
      required: true,
      unique: true,
      uppercase: true,
      trim: true,
    },
    title: {
      type: String,
      required: [true, 'Test title is required'],
      trim: true,
    },
    description: {
      type: String,
      default: '',
    },
    examinerId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User',
      required: true,
    },
    testPassword: {
      type: String,
      required: [true, 'Test entry password is required'],
      trim: true,
    },
    startTime: {
      type: Date,
      required: [true, 'Start time is required'],
    },
    endTime: {
      type: Date,
      required: [true, 'End time is required'],
    },
    registrationDeadline: {
      type: Date,
      required: [true, 'Registration deadline is required'],
    },
    registrationFields: [registrationFieldSchema],
    requirePhoto: {
      type: Boolean,
      default: true,
    },
    questions: [questionSchema],
    totalMarks: {
      type: Number,
      default: 0,
    },
  },
  { timestamps: true }
);

testSchema.pre('save', function (next) {
  if (this.questions && this.questions.length > 0) {
    this.totalMarks = this.questions.reduce((sum, q) => sum + (Number(q.marks) || 0), 0);
  } else {
    this.totalMarks = 0;
  }
  next();
});

module.exports = mongoose.model('Test', testSchema);
