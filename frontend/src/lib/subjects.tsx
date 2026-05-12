import React from 'react';
import type { SubjectInfo } from '../hooks/useApi';
import type { Subject } from '../store/useChatStore';
import { AtomIcon, CalculatorIcon, DnaIcon, FlaskIcon } from '../components/Icons';

export const DEFAULT_SUBJECTS: SubjectInfo[] = [
  {
    id: 'physics',
    name: 'Physics',
    name_lg: 'Fizikisi',
    icon: 'atom',
    color: '#3b82f6',
    starter_prompts: [
      "Explain Newton's Second Law with a worked example",
      'How do I solve projectile motion problems?',
      "Nnyonnyola Ohm's Law (Explain Ohm's Law in Luganda)",
      'What is the photoelectric effect?',
    ],
  },
  {
    id: 'chemistry',
    name: 'Chemistry',
    name_lg: 'Kemisutti',
    icon: 'flask',
    color: '#10b981',
    starter_prompts: [
      'Explain the SN2 reaction mechanism step by step',
      'How do I balance redox equations?',
      "What is Le Chatelier's Principle?",
      'Describe the properties of Group 7 elements',
    ],
  },
  {
    id: 'biology',
    name: 'Biology',
    name_lg: 'Bayoloji',
    icon: 'dna',
    color: '#f59e0b',
    starter_prompts: [
      'Explain the stages of mitosis with diagrams',
      'How does photosynthesis work?',
      'Nnyonnyola DNA replication (Explain DNA replication)',
      'What is natural selection?',
    ],
  },
  {
    id: 'mathematics',
    name: 'Mathematics',
    name_lg: 'Okubala',
    icon: 'calculator',
    color: '#8b5cf6',
    starter_prompts: [
      'How do I integrate by parts?',
      'Solve: x² - 5x + 6 = 0 using the quadratic formula',
      'Prove the chain rule for differentiation',
      'What is the binomial distribution?',
    ],
  },
];

export const GENERAL_STARTER_PROMPTS = [
  "Newton's Second Law",
  'What is mitosis?',
  'Differentiation rules',
  'SN2 mechanism',
];

export const FOLLOW_UP_PROMPTS = [
  'Give me a practice problem',
  'Explain that in simpler terms',
  'Show a worked example',
  'Test me on this topic',
];

const iconMap: Record<string, React.ReactNode> = {
  atom: <AtomIcon />,
  flask: <FlaskIcon />,
  dna: <DnaIcon />,
  calculator: <CalculatorIcon />,
};

export function getSubjectRegistry(subjects?: SubjectInfo[]): SubjectInfo[] {
  return subjects && subjects.length > 0 ? subjects : DEFAULT_SUBJECTS;
}

export function getSubjectInfo(subject: Subject | string | null | undefined, subjects?: SubjectInfo[]) {
  if (!subject) return null;
  return getSubjectRegistry(subjects).find((item) => item.id === subject) ?? null;
}

export function getSubjectPrompts(subject: Subject, subjects?: SubjectInfo[]): string[] {
  if (!subject) return GENERAL_STARTER_PROMPTS;
  return getSubjectInfo(subject, subjects)?.starter_prompts ?? [];
}

export function renderSubjectIcon(icon: string): React.ReactNode {
  return iconMap[icon] ?? <AtomIcon />;
}
