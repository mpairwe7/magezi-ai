import React, { memo } from 'react';
import { SparklesIcon, BookIcon } from './Icons';
import { Subject } from '../store/useChatStore';
import type { SubjectInfo } from '../hooks/useApi';
import { GENERAL_STARTER_PROMPTS, getSubjectPrompts } from '../lib/subjects';

interface StarterPromptsProps {
  subject: Subject;
  onSelect: (prompt: string) => void;
  subjects?: SubjectInfo[];
}

function StarterPromptsInner({ subject, onSelect, subjects }: StarterPromptsProps) {
  const prompts = subject ? getSubjectPrompts(subject, subjects) : GENERAL_STARTER_PROMPTS;

  return (
    <aside className="card">
      <header className="section-title">
        <div>
          <h3>Try asking</h3>
          <span className="small">
            {subject ? `${subject.charAt(0).toUpperCase() + subject.slice(1)} questions` : 'Select a subject or just ask'}
          </span>
        </div>
        <div className="pill"><SparklesIcon /> Suggestions</div>
      </header>
      <div className="chip-grid">
        {(prompts ?? []).map((p) => (
          <button key={p} className="chip" onClick={() => onSelect(p)}>
            <SparklesIcon /> {p}
          </button>
        ))}
      </div>
      <div className="panel-note">
        <h4>How Magezi teaches</h4>
        <ul>
          <li><strong>Explain</strong> — Clear concept explanation</li>
          <li><strong>Example</strong> — Fully worked solution</li>
          <li><strong>Activity</strong> — Real-world connection</li>
          <li><strong>Try It</strong> — Practice problem for you</li>
          <li><strong>Feedback</strong> — Check your working</li>
        </ul>
      </div>
      <div className="panel-note">
        <h4>NCDC 2025 Curriculum</h4>
        <ul>
          <li>Every answer cites the official NCDC syllabus.</li>
          <li>Competence-based — focused on understanding, not memorising.</li>
          <li>UNEB past paper references where available.</li>
          <li>4 languages: English, Luganda, Swahili, Runyankole.</li>
        </ul>
      </div>
      <div className="panel-note">
        <h4><BookIcon /> Remember</h4>
        <p style={{ margin: 0, fontStyle: 'italic', color: 'var(--accent-gold)' }}>
          "Magezi empowers you — it does not replace your teacher.
          Always verify important answers with your teacher."
        </p>
      </div>
    </aside>
  );
}

const StarterPrompts = memo(StarterPromptsInner);
export default StarterPrompts;
