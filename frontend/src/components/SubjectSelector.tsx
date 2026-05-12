import React, { memo } from 'react';
import { Subject } from '../store/useChatStore';
import type { SubjectInfo } from '../hooks/useApi';
import { getSubjectRegistry, renderSubjectIcon } from '../lib/subjects';

interface SubjectSelectorProps {
  selected: Subject;
  onSelect: (subject: Subject) => void;
  subjects?: SubjectInfo[];
}

function SubjectSelectorInner({ selected, onSelect, subjects }: SubjectSelectorProps) {
  const options = getSubjectRegistry(subjects);
  return (
    <div className="subject-selector" role="group" aria-label="Subject selection">
      {options.map((subject) => (
        <button
          key={subject.id}
          className="subject-btn"
          data-subject={subject.id}
          aria-pressed={selected === subject.id}
          onClick={() => onSelect(selected === subject.id ? null : subject.id as Subject)}
        >
          {renderSubjectIcon(subject.icon)} {subject.name}
        </button>
      ))}
    </div>
  );
}

const SubjectSelector = memo(SubjectSelectorInner);
export default SubjectSelector;
