'use client';

import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown } from 'lucide-react';

interface FilterButtonProps {
  label: string;
  isOpen: boolean;
  isActive: boolean;
  onClick: () => void;
  children: ReactNode;
  onClickOutside: () => void;
}

export function FilterButton({
  label,
  isOpen,
  isActive,
  onClick,
  children,
  onClickOutside,
}: FilterButtonProps) {
  const ref = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);
  const isClient = useSyncExternalStore(
    () => () => undefined,
    () => true,
    () => false
  );

  const handleClick = () => {
    if (!isOpen && ref.current) {
      const button = ref.current.querySelector('button');
      if (button) {
        const rect = button.getBoundingClientRect();
        setPosition({
          top: rect.bottom + 8,
          left: rect.left,
        });
      }
    }
    onClick();
  };

  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      const inButton = ref.current?.contains(target);
      const inDropdown = dropdownRef.current?.contains(target);
      if (!inButton && !inDropdown) {
        onClickOutside();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen, onClickOutside]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={handleClick}
        aria-expanded={isOpen}
        className={`flex items-center gap-1.5 px-3 py-2 rounded-full border text-sm transition-colors ${
          isActive
            ? 'bg-purple-100 border-purple-300 text-purple-700'
            : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'
        } ${isOpen ? 'ring-2 ring-purple-500 ring-offset-1' : ''}`}
      >
        <span>{label}</span>
        <ChevronDown size={16} className={`transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isClient && isOpen && position
        ? createPortal(
            <div
              ref={dropdownRef}
              className="fixed bg-white rounded-lg shadow-xl border border-gray-100 z-[9999] min-w-[250px] animate-in fade-in slide-in-from-top-2 duration-200"
              style={{ top: position.top, left: position.left }}
            >
              {children}
            </div>,
            document.body
          )
        : null}
    </div>
  );
}
